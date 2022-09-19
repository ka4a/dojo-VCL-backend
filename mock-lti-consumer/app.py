import time
import json
from os import environ
from pathlib import Path

import requests
import jwt
import serverless_wsgi
from flask import Flask, make_response, request, jsonify


app = Flask(__name__)
WEB_ADDRESS = environ["WEB_ADDRESS"]
MOCK_ADDRESS = environ["MOCK_ADDRESS"]


roles = {
    "student": ["http://purl.imsglobal.org/vocab/lis/v2/institution/person#Student"],
    "instructor": ["http://purl.imsglobal.org/vocab/lis/v2/institution/person#Instructor"],
}
payload = {
    "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiResourceLinkRequest",
    "https://purl.imsglobal.org/spec/lti/claim/version": "1.3.0",
    "iss": f"{MOCK_ADDRESS}",
    "aud": "04ddd4ef-086b-499a-8c3a-0ae46de38097",
    "azp": "04ddd4ef-086b-499a-8c3a-0ae46de38097",
    "https://purl.imsglobal.org/spec/lti/claim/deployment_id": "1",
    "https://purl.imsglobal.org/spec/lti/claim/target_link_uri": (f"{MOCK_ADDRESS}/lti/launch/"),
    "https://purl.imsglobal.org/spec/lti/claim/resource_link": {
        "id": "block-v1:ExampleKK+1+2022+type@lti_consumer+block@61ee9873a1cf4dac8053494e2eead36e"
    },
    "sub": "902b04c6-ab9d-46fb-b05a-7dc46abb1f2d",
    "https://purl.imsglobal.org/spec/lti/claim/roles": [],
    "https://purl.imsglobal.org/spec/lti/claim/launch_presentation": {"document_target": "iframe"},
    "https://purl.imsglobal.org/spec/lti/claim/context": {
        "id": "course-v1:ExampleKK+1+2022",
        "type": ["http://purl.imsglobal.org/vocab/lis/v2/course#CourseOffering"],
        "title": "Advanced Javascript - ExampleKK",
        "label": "course-v1:ExampleKK+1+2022",
    },
    "https://purl.imsglobal.org/spec/lti-ags/claim/endpoint": {
        "scope": [
            "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem",
            "https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly",
            "https://purl.imsglobal.org/spec/lti-ags/scope/score",
        ],
        "lineitems": f"{MOCK_ADDRESS}/api/lti_consumer/v1/lti/12/lti-ags",
    },
    "https://purl.imsglobal.org/spec/lti-nrps/claim/namesroleservice": {
        "context_memberships_url": (f"{MOCK_ADDRESS}/api/lti_consumer/v1/lti/12/memberships"),
        "service_versions": ["2.0"],
    },
    "nonce": "test-uuid-1234",
    "iat": time.time(),
    "exp": time.time() + 60 * 60 * 24,
}

public_key = Path("public.key").read_text()
private_key = Path("private.key").read_text()
public_jwt_json = Path("public.jwt.json").read_text()
access_token = Path("token.json").read_text()
membership_data = Path("membership.json").read_text()


def get_launch_user(request):
    __, launch_user_id, role = request.args.get("redirect_uri").rsplit("/", 2)
    return launch_user_id, role


@app.route("/lti/login/", methods=["GET"])
def login():
    query_params = request.query_string.decode("utf-8")
    login_url = f"{WEB_ADDRESS}/lti/login/?{query_params}"
    login_response = requests.get(login_url, allow_redirects=False)
    headers = login_response.headers
    launch_url = headers["Location"]
    response = requests.get(launch_url, cookies=dict(login_response.cookies.items()), headers=headers)
    return (response.text, response.status_code, response.headers.items())


@app.route("/api/lti_consumer/v1/launch/", methods=["GET"])
def launch():
    payload["nonce"] = request.args.get("nonce")
    client_id = request.args.get("client_id")
    launch_user_id, role = get_launch_user(request)
    payload["iss"] = f"{MOCK_ADDRESS}"
    payload["sub"] = str(launch_user_id)
    payload["aud"] = payload["azp"] = str(client_id)
    payload["https://purl.imsglobal.org/spec/lti/claim/roles"] = roles[role]
    resp = requests.post(
        f"{WEB_ADDRESS}/lti/launch/",
        {
            "state": request.args["state"],
            "id_token": jwt.encode(
                payload,
                private_key,
                "RS256",
                {"alg": "RS256", "kid": "0c65e4a4-9695-4d35-8adf-35e6debc1ff0"},
            ),
        },
        cookies=dict(request.cookies.items()),
    )
    headers = dict(
        resp.headers,
        launch_params=request.query_string.decode("utf-8"),
        launch_cookies=json.dumps(dict(request.cookies.items())),
    )
    return (resp.text, resp.status_code, headers.items())


@app.route("/lti/api/submission/<lti_launch_state>/<wa_id>/", methods=["POST"])
def submit(lti_launch_state, wa_id):
    cookies = dict(request.cookies.items())
    resp = requests.post(
        f"{WEB_ADDRESS}/lti/api/submission/{lti_launch_state}/{wa_id}/",
        cookies=cookies,
    )
    return (resp.text, resp.status_code, resp.headers.items())


@app.route("/lti/api/score/<lti_launch_state>/<wa_id>/", methods=["POST"])
def score(lti_launch_state, wa_id):
    cookies = dict(request.cookies.items())
    resp = requests.post(
        f"{WEB_ADDRESS}/lti/api/score/{lti_launch_state}/{wa_id}/",
        cookies=cookies,
        data={"score": request.form["score"], "comment": request.form["comment"]},
    )
    return (resp.text, resp.status_code, resp.headers.items())


@app.route("/api/lti_consumer/v1/lti/12/lti-ags", methods=["GET", "POST"])
def lti_ags():
    lineitems = [
        {
            "id": f"{MOCK_ADDRESS}/api/lti_consumer/v1/lti/12/lti-ags/47",
            "scoreMaximum": 100,
            "label": "LTI Consumer",
            "resourceId": "block-v1:ExampleKK+1+2022+type@lti_consumer+block@61ee9873a1cf4dac8053494e2eead36e",
            "resourceLinkId": "block-v1:ExampleKK+1+2022+type@lti_consumer+block@61ee9873a1cf4dac8053494e2eead36e",
            "tag": "1",
        }
    ]
    return jsonify(lineitems)


@app.route("/api/lti_consumer/v1/lti/12/lti-ags/47/scores/", methods=["POST"])
def scores():
    return request.json


@app.route("/api/lti_consumer/v1/public_keysets/<path:path>", methods=["GET", "POST"])
def keysets(path):
    resp = make_response(public_jwt_json)
    resp.headers["Content-Type"] = "application/json"
    resp.headers["Content-Disposition"] = "attachment;filename=keyset.json"
    return resp


@app.route("/api/lti_consumer/v1/token/<path:path>", methods=["POST"])
def token(path):
    return access_token


@app.route("/api/lti_consumer/v1/lti/12/memberships", methods=["POST", "GET"])
def memberships():
    return membership_data


def handler(event, context):
    return serverless_wsgi.handle_request(app, event, context)


if __name__ == "__main__":
    app.run(host="localhost", port="8080")
