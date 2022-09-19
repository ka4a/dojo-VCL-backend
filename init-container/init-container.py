import argparse
from time import sleep
import git
import logging
import os
import sys
from urllib.parse import urlparse
from git.util import rmtree

from vcl_utils.logging import configure_logging


try:
    WS_PUID = int(os.environ["WS_PUID"])
    WS_PGID = int(os.environ["WS_PGID"])
except (TypeError, KeyError):
    raise Exception("WS_PUID and WS_PGID env variables must be defined.")

configure_logging(app_name="init-container")
logger = logging.getLogger(__name__)


def chown(path, puid=WS_PUID, pgid=WS_PGID, recursive=True):
    os.chown(path, puid, pgid)
    if not recursive:
        return
    for root, dirs, files in os.walk(path):
        for dir in dirs:
            os.chown(os.path.join(root, dir), puid, pgid)
        for file in files:
            os.chown(os.path.join(root, file), puid, pgid)


def create_directory(path, user_accessible=False):
    logger.info(f"Creating directory {path}.")
    if not os.path.exists(path):
        os.makedirs(path)
        logger.info(f"{path} directory created.")
    else:
        logger.info(f"Directory {path} already exist. Skipping.")
    if user_accessible:
        logger.info(f"Setting permission for {path} to UID:{WS_PUID}, GID:{WS_PGID}.")
        chown(path)


def make_private_repo_url(url, gh_token):
    # Build a repo url in the format 'https://<access_token>:x-oauth-basic@github.com/username/private-project'
    url_params = urlparse(url)
    return url_params._replace(netloc=f"{gh_token}:x-oauth-basic@{url_params.netloc}").geturl()


def reset_repo(folder):
    logger.info(f"Resetting repo at {folder}.")
    rmtree(os.path.join(folder, ".git"))
    local_repo = git.Repo.init(folder)
    local_repo.config_writer().set_value("user", "name", "Workspace Committer").release()
    local_repo.config_writer().set_value("user", "email", "wokspace@container.init").release()
    local_repo.git.add(all=True)
    local_repo.git.commit("-m", "Happy coding!")


def checkout_repo(repo_url, folder, gh_token=None):

    if os.path.exists(folder):
        # skip the checkout if directory is non-empty
        if os.path.isdir(folder) and len(os.listdir(folder)) > 0:
            logger.info(f"Skipping checkout as the folder '{folder}' is not empty.")
            return
    else:
        create_directory(folder, user_accessible=True)

    logger.info(f"Cloning repo {repo_url} into {folder}.")
    try:
        git.Repo.clone_from(repo_url, folder)
    except git.exc.GitCommandError:
        logger.info("Detected private repo")
        # Might be a private repo
        if not gh_token:
            logger.error("Missing GitHub access token, cannot checkout private repo.")
            sys.exit(1)
        private_url = make_private_repo_url(repo_url, gh_token)
        git.Repo.clone_from(private_url, folder)

    # Sharing .git folder would share the git auth token
    # and would allow workspace users to push to private folders
    reset_repo(folder)
    chown(folder)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Init a workspace container.")

    parser.add_argument(
        "--repo",
        default=os.environ.get("ASSIGNMENT_REPO"),
        help="Repo with the code to checkout",
    )

    parser.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        help="Runs container in infinite loop when passed",
    )
    parser.add_argument(
        "--gh-token",
        default=os.environ.get("GH_ACCESS_TOKEN"),
        help="GitHub access token for the private repo",
    )

    args = parser.parse_args()

    if args.debug:
        while True:
            logger.info("Waiting in loop to allow debugging. Set debug to False in Workspace Allocation to disable")
            sleep(1)

    folders = {
        "home": {"path": os.environ.get("USER_HOME_FOLDER", "/home/coder")},
        "assignment": {"path": os.environ.get("USER_ASSIGNMENT_FOLDER", "/home/coder/assignment")},
        "coder_configs": {"path": os.environ.get("CODER_CONFIG_FOLDER", "/home/coder/.config")},
    }

    create_directory(folders["home"]["path"], user_accessible=True)

    checkout_repo(
        args.repo,
        folders["assignment"]["path"],
        gh_token=args.gh_token,
    )
