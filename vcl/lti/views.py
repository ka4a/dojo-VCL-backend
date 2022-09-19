import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from pylti1p3.contrib.django import DjangoOIDCLogin
from pylti1p3.contrib.django.lti1p3_tool_config.models import LtiTool
from pylti1p3.deep_link_resource import DeepLinkResource
from pylti1p3.exception import LtiException, OIDCException, LtiServiceException
from pylti1p3.grade import Grade
from pylti1p3.lineitem import LineItem

from assignment.models import Submission, WorkspaceAllocation, WorkspaceStatus, WorkspaceUser
from assignment.tasks import terminate_workspace_session
from assignment.api.v1.permissions import IsWorkspaceUser

from .utils import get_launch_data_storage, get_tool_conf, ExtendedDjangoMessageLaunch

logger = logging.getLogger(__name__)


class AssignmentConfigurationError(Exception):
    pass


def get_ctx_from_lti_service_exception(exc: LtiServiceException, user: WorkspaceUser, instructor_message: str = None):
    context = {"message": "Failed to launch assignment. Please contact your instructor."}
    if user.is_instructor():
        context["message"] = f"{instructor_message} [status_code={exc.response.status_code}] | Response:"
        context["extra_info"] = exc.response.text

    return context


def get_launch_url(request):
    logger.info("Getting launch url")
    target_link_uri = request.POST.get("target_link_uri", request.GET.get("target_link_uri"))

    if not target_link_uri:
        raise Exception('Missing "target_link_uri" param')
    return target_link_uri


def login(request):
    tool_conf = get_tool_conf()
    launch_data_storage = get_launch_data_storage()

    oidc_login = DjangoOIDCLogin(request, tool_conf, launch_data_storage=launch_data_storage)
    target_link_uri = get_launch_url(request)

    student_id = request.GET.get("student_id")

    try:
        red = oidc_login.enable_check_cookies()

        # It appears like edx is not sending Custom Parameters.
        # In this case we will use a url parameter on the login request
        # to send the student_id and then pass it to launch with pass_params_to_launch
        if student_id:
            red = red.pass_params_to_launch({"student_id": student_id})
        response = red.redirect(target_link_uri)
    except OIDCException:
        message = "OIDC login failed."
        logger.exception(message)
        response = render(
            request,
            "feedback.html",
            context={
                "message": f"{message} Please contact your instructor.",
            },
        )
    except LtiException as exc:
        message = "OIDC login failed"
        logger.exception(message)
        response = render(
            request,
            "feedback.html",
            context={
                "message": f"{message}{f'({exc.args[0]})' if exc.args else ''}. Please contact your instructor.",
            },
        )

    return response


def debug_launch_data(message_launch):

    if message_launch.is_resource_launch():
        logger.info("## Resource Launch!")
    elif message_launch.is_deep_link_launch():
        # TODO: we can use Deep Linking to configure the assignment
        logger.info("## Deep Linking Launch!")
    else:
        logger.info("## Unknown launch type")

    if message_launch.has_ags():
        logger.info("## Has Assignments and Grades Service")

    # This is not supported on edX LTI consumer
    if message_launch.is_data_privacy_launch():
        logger.info("## Is a Data Privacy launch")
        data_user = message_launch.get_data_privacy_launch_user()  # noqa
    else:
        logger.info("## Not a data privacy launch")

    # This is not supported on edX LTI consumer, this will never be triggered
    if message_launch.is_submission_review_launch():
        logger.info("## Is a submission review launch")
        review_user = message_launch.get_submission_review_user()  # noqa
        ags = message_launch.get_ags()
        lineitem = ags.get_lineitem()
        submission_review = lineitem.get_submission_review()  # noqa
    else:
        logger.info("## It's not a submission review launch")


def get_user_data_from_membership(message_launch, user_id):
    workspace_user_data = None
    if message_launch.has_nrps():
        logger.info("Found NRPS service for user=%s", user_id)
        nrps = message_launch.get_nrps()
        members = nrps.get_members()
        for member in members:
            if member["user_id"] == user_id:
                workspace_user_data = member
                break
    else:
        logger.info("NRPS Service is not available for user=%s", user_id)
        raise AssignmentConfigurationError("Names and Roles service is not enabled.")

    return workspace_user_data


def check_assignment_configuration(client_id, user):
    def raise_assignment_configuration_error(user, instructor_message: str):
        default_message = "Unable to launch the workspace. Please contact your instructor."
        if user.is_instructor():
            raise AssignmentConfigurationError(instructor_message)
        raise AssignmentConfigurationError(default_message)

    # Retrieve LtiTool
    tool = LtiTool.objects.filter(client_id=client_id).first()
    if not tool:
        logger.warning("Launching workspace: No Tool found ")
        raise_assignment_configuration_error(user, "Tool is not configured.")

    logger.info("Launching workspace: Tool found")
    # Define logic to use right tools, we'll pick the first as example
    if not hasattr(tool, "assignment"):
        logger.warning("Launching workspace: Assignment not configured")
        raise_assignment_configuration_error(user, "Assignment not configured")

    assignment = tool.assignment
    logger.info("Launching workspace: Assignment found: %s", tool.assignment.name)
    if not hasattr(assignment, "workspace_configuration"):
        logger.warning("Launching workspace: Assignment workspace not configured")
        raise_assignment_configuration_error(user, f"Workspace not configured for assignment {assignment.id}")

    return assignment


def get_or_create_workspace_allocation(launch_user, student_id, assignment):
    workspace_allocation = None

    if launch_user.is_instructor() and student_id:
        # If an instructor is reviewing student work,
        # we need to launch the student workspace and provide a scoring UI
        try:
            student = WorkspaceUser.objects.get(id=student_id)
        except WorkspaceUser.DoesNotExist:
            error = f"Student with id {student_id} is not registed on VCL"
            return workspace_allocation, error

        try:
            workspace_allocation = WorkspaceAllocation.objects.get(
                assignment=assignment,
                learner=student,
            )

            logger.info(
                f"Launching workspace: A workspace allocation for student {student_id}"
                f"assignment {assignment.id} was found, lunching by instructor {launch_user.id}."
            )
        except WorkspaceAllocation.DoesNotExist:
            error = f"Workspace allocation not found for student id {student_id}"
            return workspace_allocation, error

    else:
        workspace_allocation, created = WorkspaceAllocation.objects.get_or_create(
            assignment=assignment,
            learner=launch_user,
        )
        if created:
            logger.info(
                f"Launching workspace: A workspace allocation for user {launch_user.id} "
                f"assignment {assignment.id} didn't exist already. Created a new allocation."
            )
    return workspace_allocation, None


def launch_workspace(workspace_allocation, launch_user):
    logger.info(f"Launching workspace for user: {launch_user}")
    if launch_user.is_instructor():
        workspace_allocation.launch_workspace_async(instructor=launch_user)
    else:
        workspace_allocation.launch_workspace_async()


def get_student_previous_scores(message_launch, student_id, workspace_allocation):
    """
    NOTE: not used anywhere, keeping for potential future use.
    """

    # Get all scores for the current workspace_allocation
    ags = message_launch.get_ags()
    user_line_items = []

    # Get previous submissions generated by this workspace
    submissions = (
        Submission.objects.filter(workspace_allocation=workspace_allocation)
        .order_by("attempt_number")
        .distinct()
        .values_list("line_item_id", "status")
    )

    for submission in submissions:

        line_item_id, status = submission
        line_item = ags.find_lineitem_by_id(line_item_id)
        # get the student's grades
        grades = [grade for grade in ags.get_grades(line_item) if grade["userId"] == student_id]
        if grades:
            user_line_item = {
                "label": line_item.get_label(),
                "tag": line_item.get_tag(),
                "status": status,
                "grades": grades,
            }
            user_line_items.append(user_line_item)
    return user_line_items


def get_or_create_launch_user(launch_data):
    """
    Get or create launch user.
    """
    # Get assignment related LTI data
    launch_user_id = launch_data.get("sub")
    user_roles = launch_data.get("https://purl.imsglobal.org/spec/lti/claim/roles", [])

    # Check if the launching user exists and create one if they don't
    launch_user, user_created = WorkspaceUser.objects.get_or_create(id=launch_user_id)
    launch_user.last_access = timezone.now()
    launch_user.roles = user_roles
    launch_user.save()

    if user_created:
        logger.info("Launching workspace: Created new user {}".format(launch_user_id))

    return launch_user


def is_lti_launch_allowed(workspace_allocation, is_review_launch, resource_link_id):
    """
    Check whether a user is allowed to launch LTI.

    Student cannot launch if:
        -> last submission is in grading phase
        -> last submission is rejected but no attempts are remaining
        -> last submission is passed
    Instructor cannot launch if:
        -> student hasn't submitted yet
        -> the student submission was graded
    """
    result = True, None
    submission = workspace_allocation.get_last_submission_for_resource(resource_link_id)
    if is_review_launch:
        if not submission:
            result = False, "This student has not submitted the assignment yet."
        elif submission.status != Submission.Status.GRADING:
            result = False, "This student does not have any submission due on grading."
    elif submission:
        if submission.status == Submission.Status.GRADING:
            result = False, "Grading in progress, new submissions are not allowed."
        elif submission.status == Submission.Status.PASSED:
            result = False, "You are already passed."
        elif (
            submission.status == Submission.Status.REJECTED
            and workspace_allocation.remaining_attempts_for_resource(resource_link_id) == 0
        ):
            result = False, "Max number of attempts reached."

    return result


def get_or_create_launch(request):
    """
    Retrieve or initialize LTI launch.
    """
    tool_conf = get_tool_conf()
    launch_data_storage = get_launch_data_storage()

    # Get launch from cache OR initialize new launch
    if launch_id := request.session.get("lti-launch-id"):
        try:
            return ExtendedDjangoMessageLaunch.from_cache(
                launch_id, request, tool_conf, launch_data_storage=launch_data_storage
            )
        except LtiException:
            # launch id has expired, let's
            # create new launch
            pass

    message_launch = ExtendedDjangoMessageLaunch(request, tool_conf, launch_data_storage=launch_data_storage)
    request.session["lti-launch-id"] = message_launch.get_launch_id()
    return message_launch


@csrf_exempt
@require_POST
def launch(request):
    def get_launch_error_feedback_ctx(user: WorkspaceUser, instructor_message: str):
        ctx = {"message": "Failed to launch assignment. Please contact your instructor."}
        if user and user.is_instructor():
            ctx["message"] = instructor_message
        return ctx

    # Init data
    create_submission_url = None
    score_submission_url = None
    student_id = None

    message_launch = get_or_create_launch(request)

    launch_user = None
    try:
        launch_data = message_launch.get_launch_data()
        launch_user = get_or_create_launch_user(launch_data)
    except LtiException as exc:
        message = "LTI launch failed"
        logger.exception(message)
        return render(
            request,
            "feedback.html",
            context=get_launch_error_feedback_ctx(
                launch_user,
                instructor_message=f"{message}{f'({exc.args[0]})' if exc.args else ''}.",
            ),
        )

    # Handle the case where an instructor is launching a student workspace
    if launch_user.is_instructor():

        # We send student_id as login url parameters since
        # edx does not support message_launch.is_submission_review_launch

        login_params = message_launch.get_params_from_login()
        if login_params:
            student_id = login_params.get("student_id")
            if not student_id:
                return render(request, "feedback.html", {"message": "Student ID is missing in review launch"})

            logger.info("Launching workspace: Student ID parameter: {}".format(student_id))

    if settings.DEBUG:
        debug_launch_data(message_launch)

    try:
        # Get learner information from the launch
        # if instructor is launching, learner is `student_id`
        # Otherwise `launch_user` itself is a learner
        workspace_user_data = get_user_data_from_membership(
            message_launch, student_id if student_id else str(launch_user.id)
        )
    except LtiServiceException as exc:
        message = "Unable to retrieve user membership data"
        logger.exception(f"{message} for {launch_user.id}")
        return render(
            request,
            template_name="feedback.html",
            context=get_ctx_from_lti_service_exception(exc, launch_user, instructor_message=message),
        )
    except AssignmentConfigurationError as exc:
        message = exc.args[0]
        logger.exception(message)
        return render(
            request,
            template_name="feedback.html",
            context=get_launch_error_feedback_ctx(launch_user, instructor_message=message),
        )

    # We give access if the launch user is an instructor or if they are enrolled in the course
    if not launch_user.is_instructor() and not workspace_user_data:
        return render(request, "feedback.html", {"message": "You're not enrolled into the course."})

    if client_id := launch_data.get("azp"):
        try:
            assignment = check_assignment_configuration(client_id, launch_user)
        except AssignmentConfigurationError as exc:
            return render(
                request,
                "feedback.html",
                context=get_launch_error_feedback_ctx(launch_user, instructor_message=exc.args[0]),
            )

        workspace_allocation, error = get_or_create_workspace_allocation(launch_user, student_id, assignment)
        if not workspace_allocation:
            return render(request, "feedback.html", {"message": error})

        # Check whether the user is allowed to launch workspace.
        resource_link_id = launch_data.get("https://purl.imsglobal.org/spec/lti/claim/resource_link", {}).get("id")
        is_launch_allowed, error_message = is_lti_launch_allowed(
            is_review_launch=launch_user.is_instructor() and student_id,
            workspace_allocation=workspace_allocation,
            resource_link_id=resource_link_id,
        )
        if not is_launch_allowed:
            return render(request, "feedback.html", {"message": error_message})

        create_submission_url = reverse(
            "lti:lti-create-submission",
            kwargs={
                "launch_id": message_launch.get_launch_id(),
                "workspace_allocation_id": workspace_allocation.id,
            },
        )

        launch_workspace(workspace_allocation, launch_user)
        workspace_launch_url = (
            workspace_allocation.workspace_url
            if workspace_allocation.workspace_status == WorkspaceStatus.RUNNING
            else reverse("assignment:workspace-launch-page")
        )

        # create a workspace user session.
        request.session["workspace_user_id"] = str(launch_user.id)
        request.session["workspace_allocation_id"] = workspace_allocation.id
        if workspace_session := workspace_allocation.get_active_session():
            # keeping for logging purposes
            request.session["workspace_session_id"] = str(workspace_session.id)

        if launch_user.is_instructor() and student_id:
            # We show the scoring UI only to instructors.
            # In principle we should also check if this is a review launch
            # but it's useful during development to score own submissions.
            score_submission_url = reverse(
                "lti:lti-score-submission",
                kwargs={
                    "launch_id": message_launch.get_launch_id(),
                    "workspace_allocation_id": workspace_allocation.id,
                },
            )
            # user_line_items = get_student_previous_scores(message_launch, student_id, workspace_allocation)
            return render(
                request,
                "instructor.html",
                {
                    "assignment_name": assignment.name,
                    "user_id": str(launch_user.id),
                    "launch_page_url": workspace_launch_url,
                    "score_submission_url": score_submission_url,
                    # "line_items": reversed(user_line_items),
                    "workspace_user_data": workspace_user_data,
                },
            )
        else:
            return render(
                request,
                "student.html",
                {
                    "assignment": assignment,
                    "remaining_attempts": workspace_allocation.remaining_attempts_for_resource(resource_link_id),
                    "launch_page_url": workspace_launch_url,
                    "create_submission_url": create_submission_url,
                    "workspace_user_data": workspace_user_data,
                },
            )

    return render(
        request,
        "feedback.html",
        context=get_launch_error_feedback_ctx(
            launch_user,
            instructor_message="Client ID is missing. Please configure LTI Tool's client ID from LTI Consumer.",
        ),
    )


# TODO: Figure out if we need this
def get_jwks(request):
    logger.info("Getting JWKS")
    tool_conf = get_tool_conf()
    return JsonResponse(tool_conf.get_jwks(), safe=False)


# TODO: We can use this to configure assignments and workspaces from DeepLinking
def configure(request, launch_id, difficulty):
    tool_conf = get_tool_conf()
    launch_data_storage = get_launch_data_storage()
    message_launch = ExtendedDjangoMessageLaunch.from_cache(
        launch_id, request, tool_conf, launch_data_storage=launch_data_storage
    )

    if not message_launch.is_deep_link_launch():
        return HttpResponseForbidden("Must be a deep link!")

    launch_url = request.build_absolute_uri(reverse("lti:lti-launch") + "?difficulty=" + difficulty)

    resource = DeepLinkResource()
    resource.set_url(launch_url).set_custom_params({"difficulty": difficulty}).set_title(
        "Breakout " + difficulty + " mode!"
    )

    html = message_launch.get_deep_link().output_response_form([resource])
    return HttpResponse(html)


@csrf_exempt
@require_POST
def submit(request, launch_id, workspace_allocation_id):
    # On edX we create submission on post save of AgsScore models.
    # On submission creation, we also create tickets for graders.
    # In order to create submission we send scores in Submitted status via LTI.
    tool_conf = get_tool_conf()
    launch_data_storage = get_launch_data_storage()
    message_launch = ExtendedDjangoMessageLaunch.from_cache(
        launch_id, request, tool_conf, launch_data_storage=launch_data_storage
    )
    if not message_launch.has_ags():
        return render(
            request,
            "feedback.html",
            context={
                "message": "Don't have grades.",
            },
        )

    try:
        launch_data = message_launch.get_launch_data()
    except LtiException as exc:
        message = "Submission failed"
        logger.exception(message)
        return render(
            request,
            "feedback.html",
            context={
                "message": f"{message}{f'({exc.args[0]})' if exc.args else ''}. Please contact your instructor.",
            },
        )

    resource_link_id = launch_data.get("https://purl.imsglobal.org/spec/lti/claim/resource_link", {}).get("id")
    if not resource_link_id:
        return render(
            request,
            "feedback.html",
            context={
                "message": "Resource Link missing.",
            },
        )

    learner_id = launch_data.get("sub")
    timestamp = timezone.now().isoformat()

    try:
        workspace_allocation = WorkspaceAllocation.objects.get(id=workspace_allocation_id, learner_id=learner_id)
    except WorkspaceAllocation.DoesNotExist:
        return render(
            request,
            "feedback.html",
            context={
                "message": "Could not retrieve workspace allocation",
            },
        )

    assignment = workspace_allocation.assignment
    last_submission = workspace_allocation.get_last_submission_for_resource(resource_link_id)
    if last_submission:
        if last_submission.attempt_number >= assignment.max_attempts:
            return render(
                request,
                "feedback.html",
                context={
                    "message": "Max number of tries reached.",
                },
            )
        if last_submission.status == Submission.Status.GRADING:
            return render(
                request,
                "feedback.html",
                context={
                    "message": "Grading in progress, new submissions not allowed.",
                },
            )

    current_attempt_number = last_submission.attempt_number + 1 if last_submission else 1
    ags = message_launch.get_ags()

    sc = Grade()
    sc.set_score_given(0).set_score_maximum(assignment.max_score).set_timestamp(timestamp).set_activity_progress(
        "Submitted"
    ).set_grading_progress("PendingManual").set_user_id(learner_id)

    sc_line_item = LineItem()

    sc_line_item.set_resource_id(resource_link_id).set_resource_link_id(resource_link_id).set_score_maximum(
        assignment.max_score
    ).set_tag(str(current_attempt_number)).set_label("LTI Consumer")

    try:
        result = ags.put_grade(sc, sc_line_item)
        logger.info("Student '%s' Submitted successfully, response: %s", learner_id, result)
        terminate_workspace_session.apply_async(kwargs={"workspace_allocation_id": workspace_allocation.id})
    except LtiException as exc:
        message = "Submission failed"
        logger.exception(f"{message} for {learner_id}")
        return render(
            request,
            "feedback.html",
            context={
                "message": f"{message}{f'({exc.args[0]})' if exc.args else ''}.",
            },
        )

    line_item = ags.find_lineitem_by_tag(str(current_attempt_number))
    line_item_id = line_item.get_id()

    Submission.objects.create(
        workspace_allocation=workspace_allocation,
        line_item_id=line_item_id,
        resource_link_id=resource_link_id,
        attempt_number=current_attempt_number,
        status=Submission.Status.GRADING,
    )
    return render(request, "submission.html")


@csrf_exempt
@require_POST
def score(request, launch_id, workspace_allocation_id):
    # On edX we create submission on post save of AgsScore models.
    # On submission creation, we also create tickets for graders.
    # In order to create submission we send scores in Submitted status via LTI.

    try:
        workspace_allocation = WorkspaceAllocation.objects.get(id=workspace_allocation_id)
    except WorkspaceAllocation.DoesNotExist:
        return render(
            request,
            "feedback.html",
            context={
                "message": "Could not retrieve workspace allocation",
            },
        )

    assignment = workspace_allocation.assignment
    tool_conf = get_tool_conf()
    launch_data_storage = get_launch_data_storage()
    message_launch = ExtendedDjangoMessageLaunch.from_cache(
        launch_id, request, tool_conf, launch_data_storage=launch_data_storage
    )
    if not message_launch.has_ags():
        return render(
            request,
            "feedback.html",
            context={
                "message": "Don't have grades.",
            },
        )

    try:
        launch_data = message_launch.get_launch_data()
    except LtiException as exc:
        message = "Grading failed"
        logger.exception(message)
        return render(
            request,
            "feedback.html",
            context={
                "message": f"{message}{f'({exc.args[0]})' if exc.args else ''}. Please contact your instructor.",
            },
        )

    launch_user_id = launch_data.get("sub")
    launch_user = WorkspaceUser.get_or_none(id=launch_user_id)
    if not launch_user or not launch_user.is_instructor():
        return render(
            request,
            "feedback.html",
            context={
                "message": "You do not have access to score a student submission.",
            },
        )

    resource_link_id = launch_data.get("https://purl.imsglobal.org/spec/lti/claim/resource_link", {}).get("id")
    if not resource_link_id:
        return render(
            request,
            "feedback.html",
            context={
                "message": "Resource Link missing!",
            },
        )

    learner_id = str(workspace_allocation.learner.id)
    timestamp = timezone.now().isoformat()

    last_submission = workspace_allocation.get_last_submission_for_resource(resource_link_id)
    if last_submission:
        if last_submission.status != Submission.Status.GRADING:
            return render(
                request,
                "feedback.html",
                context={
                    "message": "This submission is already graded",
                },
            )
    else:
        return render(
            request,
            "feedback.html",
            context={
                "message": "Submission not found",
            },
        )

    try:
        earned_score = float(request.POST.get("score"))
    except (ValueError, TypeError):
        return render(
            request,
            "feedback.html",
            context={
                "message": "Grade should be a positive integer",
            },
        )

    comment = request.POST.get("comment")
    if not comment:
        return render(
            request,
            "feedback.html",
            context={
                "message": "Comment cannot be blank.",
            },
        )

    reject = request.POST.get("reject", False)

    logging.info(
        "Instructor '{}' is scoring line item {}. Score: {}, comment: {}, rejected: {}".format(
            launch_user_id, last_submission.line_item_id, earned_score, comment, bool(reject)
        )
    )
    ags = message_launch.get_ags()
    line_item = ags.find_lineitem_by_id(last_submission.line_item_id)

    grading_progress = "Failed" if reject else "FullyGraded"
    # Support rejection
    sc = Grade()
    sc.set_score_given(earned_score).set_comment(comment).set_score_maximum(assignment.max_score).set_timestamp(
        timestamp
    ).set_activity_progress("Completed").set_grading_progress(grading_progress).set_user_id(learner_id)

    try:
        result = ags.put_grade(sc, line_item)
        terminate_workspace_session.apply_async(kwargs={"workspace_allocation_id": workspace_allocation.id})
    except LtiException as exc:
        message = "Grading failed"
        logger.exception(f"{message} for instructor: {launch_user_id}")
        return render(
            request,
            "feedback.html",
            context={
                "message": f"{message}{f'({exc.args[0]})' if exc.args else ''}.",
            },
        )

    last_submission.status = Submission.Status.PASSED if not reject else Submission.Status.REJECTED
    last_submission.save()

    return render(request, "graded.html", {"result": result.get("body")})


class AuthCheckAPIView(APIView):
    permission_classes = (IsWorkspaceUser,)

    def get(self, request, workspace_allocation_id):
        """
        Authorize requests to student workspaces.
        """
        logger.debug("Referred from '%s'", request.headers.get("X-Forwarded-Uri"))
        if workspace_allocation_id != request.session["workspace_allocation_id"]:
            return Response(data={"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        logger.debug(
            "[Auth-Middleware] request received for WA='%s' and User='%s'",
            request.session["workspace_allocation_id"],
            request.session["workspace_user_id"],
        )
        return Response(status=status.HTTP_200_OK)
