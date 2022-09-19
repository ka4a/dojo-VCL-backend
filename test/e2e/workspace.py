import json
import logging
import unittest
from os import environ
from http import HTTPStatus
from time import sleep

import requests
from pyquery import PyQuery
from kubernetes import config, client

WAIT_TIMEOUT = int(environ.get("WAIT_TIMEOUT", default=6))
MAX_ATTEMPTS = int(environ.get("MAX_ATTEMPTS", default=30))
WEB_ADDRESS = environ["WEB_ADDRESS"]
EDX_PLATFORM_ADDRESS = environ["EDX_PLATFORM_ADDRESS"]
k8s_config = config.load_config()
api_client = client.ApiClient(k8s_config)


logger = logging.getLogger(__name__)
logging.basicConfig(format="\n%(asctime)s %(module)s %(levelname)s: %(message)s", level=logging.INFO)


class WorkspaceReadinessError(Exception):
    pass


class WorkspaceMixin:
    def assertResponse(self, response, assert_func, actual, expected):
        try:
            assert_func(expected, actual)
        except AssertionError:
            with open("debug_test.html", "w") as f:
                f.write(response.text)
            raise

    def launch_workspace(self, client_id, launch_user_id, role, student_id=None):
        login_url = (
            f"{EDX_PLATFORM_ADDRESS}/lti/login/?iss={EDX_PLATFORM_ADDRESS}&"
            f"client_id={client_id}&lti_deployment_id=1&"
            f"target_link_uri={EDX_PLATFORM_ADDRESS}/api/lti_consumer/v1/launch/{launch_user_id}/{role}&"
            f"login_hint=block-v1:ExampleKK+1+2022+type@lti_consumer+block@61ee9873a1cf4dac8053494e2eead36e&"
            f"lti_message_hint=&lti1p3_new_window=1"
        )
        if student_id:
            login_url += f"&student_id={student_id}"
        response = requests.get(login_url)
        return response

    def submit_assignment(self, launch_page):
        submission_url = self.extract_submission_url(launch_page)
        launch_cookies = launch_page.headers.pop("launch_cookies")
        response = requests.post(submission_url, cookies=dict(launch_page.cookies, **json.loads(launch_cookies)))
        return response

    def submit_assignment_scores(self, launch_page, data):
        grading_url = self.extract_grading_url(launch_page)
        launch_cookies = launch_page.headers.pop("launch_cookies")
        response = requests.post(
            grading_url,
            cookies=dict(launch_page.cookies, **json.loads(launch_cookies)),
            data=data,
        )
        return response

    def reload_launch_page(self, response):
        launch_params = response.headers.pop("launch_params")
        launch_cookies = response.headers.pop("launch_cookies")
        response = requests.get(
            f"{EDX_PLATFORM_ADDRESS}/api/lti_consumer/v1/launch/?{launch_params}",
            cookies=dict(response.cookies, **json.loads(launch_cookies)),
        )
        return response

    def get_workspace_pod_state(self, user_id):
        state = namespace = None
        is_pod_ready = False
        pods = client.CoreV1Api(api_client).list_pod_for_all_namespaces(label_selector=f"student={user_id}")
        if pods.items:
            pod = pods.items[0]
            namespace = pod.metadata.namespace
            state = pod.status.phase
            is_pod_ready = pod.status.container_statuses and pod.status.container_statuses[0].ready

        return (state, is_pod_ready, namespace)

    def wait_for_pod_readiness(self, user_id):
        logger.info("Trying to get the workspace state.")
        for attempt in range(1, MAX_ATTEMPTS + 1):
            state, is_ready, namespace = self.get_workspace_pod_state(user_id=user_id)
            if not is_ready:
                if namespace and state:
                    logger.info(f"Attempt#{attempt} waiting for '{namespace}' readiness.. state={state}")
                else:
                    logger.info(f"Attempt#{attempt} retrying to get the workspace state in {WAIT_TIMEOUT} seconds.")

                if attempt == MAX_ATTEMPTS:
                    error_message = (
                        f"Timeout while waiting for '{namespace}' to be ready "
                        f"({WAIT_TIMEOUT * MAX_ATTEMPTS} sec). The current state is {state}."
                    )
                    logger.error(error_message)
                    raise WorkspaceReadinessError(error_message) from None

                sleep(WAIT_TIMEOUT)
            else:
                logger.info(f"Workspace '{namespace}' is ready. Took {WAIT_TIMEOUT * attempt} seconds.")
                return namespace

    def get_namespace(self, namespace):
        namespaces = client.CoreV1Api(api_client).list_namespace()
        for namespace_obj in namespaces.items:
            if namespace_obj.metadata.name == namespace:
                return namespace_obj

    def wait_for_ws_to_terminate(self, namespace):
        for attempt in range(1, MAX_ATTEMPTS + 1):
            logger.info(f"#{attempt} waiting for workspace '{namespace}' to terminate.")
            sleep(WAIT_TIMEOUT)

            namespace_obj = self.get_namespace(namespace)
            if namespace_obj is None:
                logger.info(f"The workspace '{namespace}' has been terminated.")
                break

            assert (
                namespace_obj.status.phase == "Terminating"
            ), f"The workspace '{namespace}' is not in terminating state."
            if attempt == MAX_ATTEMPTS:
                error_message = (
                    f"Timeout while waiting for '{namespace}' to terminate "
                    f"({WAIT_TIMEOUT * MAX_ATTEMPTS} sec). "
                    f"The current state is {namespace_obj.status.phase}."
                )
                logger.error(error_message)
                raise AssertionError(error_message)

    def check_service(self, namespace):
        services = client.CoreV1Api(api_client).list_namespaced_service(namespace)
        self.assertEqual(len(services.items), 1)
        self.assertEqual(services.items[0].metadata.name, namespace)

    def delete_namespace(self, namespace):
        """
        Cleanup workspace namespace.
        """
        client.CoreV1Api(api_client).delete_namespace(name=namespace)

    def extract_ws_url(self, response):
        pq = PyQuery(response.text)
        return pq.find("a.btn.btn-primary").attr("href")

    def extract_submission_url(self, response):
        pq = PyQuery(response.text)
        return f"{EDX_PLATFORM_ADDRESS}/{pq.find('#confirmationModal form').attr('action')}"

    def extract_grading_url(self, response):
        pq = PyQuery(response.text)
        return f"{EDX_PLATFORM_ADDRESS}/{pq.find('div form.needs-validation').attr('action')}"

    def extract_launch_message(self, response):
        pq = PyQuery(response.text)
        return pq.find("p.text-left.lead.pt-2").text()

    def extract_submission_message(self, response):
        pq = PyQuery(response.text)
        return pq.find("div h4.lead").text()

    def extract_grading_message(self, response):
        pq = PyQuery(response.text)
        return pq.find("div div div p").text().strip()

    def extract_grading_comment(self, response):
        pq = PyQuery(response.text)
        return pq.find("div div div table tbody tr td")[7].text.strip()

    def extract_grading_score_given(self, response):
        pq = PyQuery(response.text)
        return float(pq.find("div div div table tbody tr td")[3].text.strip())

    def assertWorkspaceLaunchUrl(self, launch_user_id, workspace_slug, response):
        state, __, __ = self.get_workspace_pod_state(launch_user_id)
        if state == "Running":
            expected_workspace_url = f"{WEB_ADDRESS}/workspace/{workspace_slug}/"
            workspace_url = self.extract_ws_url(response=response)
            self.assertEqual(workspace_url, expected_workspace_url)
        else:
            expected_workspace_url = "/assignment/launch/"
            workspace_url = self.extract_ws_url(response=response)
            self.assertEqual(workspace_url, expected_workspace_url)


class TestWorkspace(unittest.TestCase, WorkspaceMixin):
    def test_student_n_instructor_workflow(self):
        """
        1. Student launches the workspace for the first time
        2. Workspace gets deployed into the k8s cluster
        3. Student submits the assignment and sees thank you note
        4. Instructor launches the student's workspace to review it
        5. Instructor submit the score and comment for student submission
        6. Instructor sees "Thank you" note with their awarded score & feedbacks
        """
        client_id = "54ddd4ef-086b-499a-8c3a-0ae46de38097"
        launch_user_id = "281b04c6-ab9d-46fb-b05a-7dc46abb1f2d"
        workspace_slug = "41d3e3f3-c2cd-478b-900a-f46a2aa479f9"
        response = self.launch_workspace(client_id, launch_user_id, role="student")
        self.assertResponse(response, self.assertEqual, response.status_code, HTTPStatus.OK)

        # assert workspace url in html response.
        self.assertWorkspaceLaunchUrl(launch_user_id, workspace_slug, response)

        # wait for workspace readiness
        namespace = self.wait_for_pod_readiness(launch_user_id)
        self.check_service(namespace)

        # reload launch page after workspace is ready and
        # assert workspace url once again.
        launch_page = self.reload_launch_page(response)
        self.assertWorkspaceLaunchUrl(launch_user_id, workspace_slug, launch_page)

        expected_message = (
            'Student1, you are about to start "TA5" assignment. Once you click "Launch workspace", '
            "your coding environment will be launched in the browser. Instructions will be available. "
            "You can work on this assignment multiple time, but you can submit solutions for it only 1 time. "
            "After you submit a solution, you will not be able to launch the workspace until "
            'your solution is graded. In order to submit a solution, click "Submit solution" below. '
            "You can get back to this page anytime from the learning portal."
        )
        actual_message = self.extract_launch_message(launch_page)
        self.assertEqual(actual_message, expected_message)

        # Student Submit the assignment
        response = self.submit_assignment(launch_page)

        # Assert that the feedback is correct and workspace is
        # terminating after the submission.
        submission_feedback = self.extract_submission_message(response)
        self.assertEqual(
            submission_feedback,
            "Thank you for submitting a solution for the coding assignment. You can close this tab now.",
        )

        # Make sure workspace has terminated
        # before instructor launch.
        self.wait_for_ws_to_terminate(namespace)
        self.assertEqual(self.get_namespace(namespace), None)

        # Now, instructor launches this student's workspace and grade it.
        instructor_id = "902b04c6-ab9d-46fb-b05a-7dc46abb1f2d"
        student_id = launch_user_id
        workspace_slug = "5462423a-0807-457c-b89f-d7d2bce99d10"

        launch_page = self.launch_workspace(client_id, instructor_id, role="instructor", student_id=student_id)

        self.assertResponse(launch_page, self.assertEqual, response.status_code, HTTPStatus.OK)
        # assert workspace url in html response.
        self.assertWorkspaceLaunchUrl(student_id, workspace_slug, launch_page)

        # wait for workspace readiness
        namespace = self.wait_for_pod_readiness(student_id)
        self.check_service(namespace)

        score, comment = 92.5, "Excellent!"
        response = self.submit_assignment_scores(launch_page, {"score": score, "comment": comment})

        grading_feedback = self.extract_grading_message(response)
        self.assertEqual(
            grading_feedback, "The student submission has been graded successfully. You can close this tab now."
        )

        self.assertEqual(self.extract_grading_comment(response), comment)
        self.assertEqual(self.extract_grading_score_given(response), score)

        self.wait_for_ws_to_terminate(namespace)
        self.assertEqual(self.get_namespace(namespace), None)

    def test_instructor_as_student_launch_workspace(self):
        """
        1. Instructor launches the workspace
        2. Workspace gets deployed into the k8s cluster
        3. HTML page correctly point to workspace launch url
        """
        client_id = "24ddd4ef-086b-499a-8c3a-0ae46de38097"
        launch_user_id = "902b04c6-ab9d-46fb-b05a-7dc46abb1f2d"
        workspace_slug = "cbf8165e-1195-45c6-bc9a-c389c224b1cb"
        response = self.launch_workspace(client_id, launch_user_id, role="instructor")
        self.assertResponse(response, self.assertEqual, response.status_code, HTTPStatus.OK)
        # assert workspace url in html response.
        self.assertWorkspaceLaunchUrl(launch_user_id, workspace_slug, response)

        # wait for workspace readiness
        namespace = self.wait_for_pod_readiness(launch_user_id)
        self.check_service(namespace)
        # reload launch page after workspace is ready and
        # assert workspace url once again.
        response = self.reload_launch_page(response)
        self.assertWorkspaceLaunchUrl(launch_user_id, workspace_slug, response)

        # cleanup workspace namespace.
        self.delete_namespace(namespace)

    def test_instructor_launch_workspace(self):
        """
        1. Instructor launches a student's workspace
        2. Workspace gets deployed into the k8s cluster
        3. HTML page correctly point to workspace launch url
        """
        client_id = "34ddd4ef-086b-499a-8c3a-0ae46de38097"
        launch_user_id = "902b04c6-ab9d-46fb-b05a-7dc46abb1f2d"
        student_id = "481b04c6-ab9d-46fb-b05a-7dc46abb1f2d"
        workspace_slug = "5462423a-0807-457c-b89f-d7d2bce99d10"

        response = self.launch_workspace(client_id, launch_user_id, role="instructor", student_id=student_id)

        self.assertResponse(response, self.assertEqual, response.status_code, HTTPStatus.OK)
        # assert workspace url in html response.
        self.assertWorkspaceLaunchUrl(student_id, workspace_slug, response)

        # wait for workspace readiness
        namespace = self.wait_for_pod_readiness(student_id)
        self.check_service(namespace)
        # reload launch page after workspace is ready and
        # assert workspace url once again.
        response = self.reload_launch_page(response)
        self.assertWorkspaceLaunchUrl(student_id, workspace_slug, response)

        # cleanup workspace namespace.
        self.delete_namespace(namespace)

    def test_student_launch_graded_workspace(self):
        """
        1. Student launches the workspace whose grading is in progress
        2. Student sees "Grading in progress, new submissions are not allowed"
        """
        client_id = "34ddd4ef-086b-499a-8c3a-0ae46de38097"
        launch_user_id = "481b04c6-ab9d-46fb-b05a-7dc46abb1f2d"
        resp = self.launch_workspace(client_id, launch_user_id, role="student")
        self.assertResponse(resp, self.assertIn, resp.text, "Grading in progress, new submissions are not allowed.")

    def test_passed_student_launch(self):
        """
        1. Student that has already passed, tries to launch workspace
        2. Student sees "You are already passed."
        """
        client_id = "24ddd4ef-086b-499a-8c3a-0ae46de38097"
        launch_user_id = "681b04c6-ab9d-46fb-b05a-7dc46abb1f2d"
        response = self.launch_workspace(client_id, launch_user_id, role="student")
        self.assertResponse(response, self.assertIn, response.text, "You are already passed.")

    def test_student_launch_wo_course_enrollment(self):
        """
        1. Student, that is not enrolled into the course, tries to launch workspace
        2. Student sees "You're not enrolled into the course."
        """
        client_id = "24ddd4ef-086b-499a-8c3a-0ae46de38097"
        launch_user_id = "781b04c6-ab9d-46fb-b05a-7dc46abb1f2d"
        response = self.launch_workspace(client_id, launch_user_id, role="student")
        self.assertResponse(response, self.assertIn, response.text, "You&#x27;re not enrolled into the course.")

    def test_student_launch_rejected_submission_no_attempts(self):
        """
        1. Student, whose submission has been rejected with no further attempts left, tries to launch workspace.
        2. Student sees "Max number of attempts reached."
        """
        client_id = "44ddd4ef-086b-499a-8c3a-0ae46de38097"
        launch_user_id = "102b04c6-ab9d-46fb-b05a-7dc46abb1f2d"
        response = self.launch_workspace(client_id, launch_user_id, role="student")
        self.assertResponse(response, self.assertIn, response.text, "Max number of attempts reached.")

    def test_instructor_launch_no_student_submission(self):
        """
        1. Instructor launches a student's workspace who hasn't submitted yet
        2. Instructor sees "This student has not submitted the assignment yet."
        """
        client_id = "54ddd4ef-086b-499a-8c3a-0ae46de38097"
        launch_user_id = "902b04c6-ab9d-46fb-b05a-7dc46abb1f2d"
        student_id = "281b04c6-ab9d-46fb-b05a-7dc46abb1f2d"
        response = self.launch_workspace(client_id, launch_user_id, role="instructor", student_id=student_id)
        self.assertResponse(
            response, self.assertIn, response.text, "This student has not submitted the assignment yet."
        )

    def test_instructor_launch_graded_student_submission(self):
        """
        1. Instructor launches a student's workspace whose submission has been graded already
        2. Instructor sees "This student does not have any submission due on grading."
        """
        client_id = "44ddd4ef-086b-499a-8c3a-0ae46de38097"
        launch_user_id = "902b04c6-ab9d-46fb-b05a-7dc46abb1f2d"
        student_id = "102b04c6-ab9d-46fb-b05a-7dc46abb1f2d"
        response = self.launch_workspace(client_id, launch_user_id, role="instructor", student_id=student_id)
        self.assertResponse(
            response, self.assertIn, response.text, "This student does not have any submission due on grading."
        )

    def test_student_cannot_launch_others_workspaces(self):
        """
        1. Student1 launches their workspace.
        2. Student2 launches their workspace.
        3. Student1 tries to access Student2's workspace through direct URL and faces 403.
        4. Student2 tries to access Student1's workspace through direct URL and faces 403.
        """
        client_id = "54ddd4ef-086b-499a-8c3a-0ae46de38097"

        student1_user_id = "112b04c6-ab9d-46fb-b05a-7dc46abb1f2d"
        student1_ws_slug = "8062423a-0807-457c-b89f-d7d2bce99d11"
        student1_launch_response = self.launch_workspace(client_id, student1_user_id, role="student")
        self.assertResponse(
            student1_launch_response, self.assertEqual, student1_launch_response.status_code, HTTPStatus.OK
        )
        student1_workspace_ns = self.wait_for_pod_readiness(student1_user_id)
        self.check_service(student1_workspace_ns)

        # Assert the the student1 can access own workspace
        student1_workspace_url = f"{WEB_ADDRESS}/workspace/{student1_ws_slug}/"
        student1_session_id = student1_launch_response.headers["set-cookie"].split("sessionid=")[-1].split("; ")[0]
        response = requests.get(student1_workspace_url, cookies={"sessionid": student1_session_id})
        self.assertEqual(response.status_code, 200)

        student2_user_id = "122b04c6-ab9d-46fb-b05a-7dc46abb1f2d"
        student2_ws_slug = "9062423a-0807-457c-b89f-d7d2bce99d11"
        student2_launch_response = self.launch_workspace(client_id, student2_user_id, role="student")
        self.assertResponse(
            student2_launch_response, self.assertEqual, student2_launch_response.status_code, HTTPStatus.OK
        )
        student2_workspace_ns = self.wait_for_pod_readiness(student2_user_id)
        self.check_service(student2_workspace_ns)

        # Assert the student2 can access own workspace
        student2_workspace_url = f"{WEB_ADDRESS}/workspace/{student2_ws_slug}/"
        student2_session_id = student2_launch_response.headers["set-cookie"].split("sessionid=")[-1].split("; ")[0]
        response = requests.get(student2_workspace_url, cookies={"sessionid": student2_session_id})
        self.assertEqual(response.status_code, 200)

        # Verify that student1 cannot access student2's workspace and vice-versa.

        # Assert the student1 cannot access student2's workspace
        student2_workspace_url = f"{WEB_ADDRESS}/workspace/{student2_ws_slug}/"
        student1_session_id = student1_launch_response.headers["set-cookie"].split("sessionid=")[-1].split("; ")[0]
        response = requests.get(student2_workspace_url, cookies={"sessionid": student1_session_id})
        self.assertEqual(response.status_code, 403)

        # Assert the student2 cannot access student1's workspace
        student1_workspace_url = f"{WEB_ADDRESS}/workspace/{student1_ws_slug}/"
        student2_session_id = student2_launch_response.headers["set-cookie"].split("sessionid=")[-1].split("; ")[0]
        response = requests.get(student1_workspace_url, cookies={"sessionid": student2_session_id})
        self.assertEqual(response.status_code, 403)

        # cleanup workspaces.
        self.delete_namespace(student1_workspace_ns)
        self.delete_namespace(student2_workspace_ns)
