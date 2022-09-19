from django.core.management import BaseCommand, CommandError
from django.core.management import call_command
from pathlib import Path
from urllib.parse import urlparse
from os import path
from django.conf import settings
import tempfile
import json


class Command(BaseCommand):
    help = "load-fixtures replaces necessary information in fixtures and load them to the connected database "

    def add_arguments(self, parser):
        parser.add_argument(
            "lti-consumer-url",
            help="URL of the LTI consumer. It will replace all URLs in LTI"
            "configuration. Example: http://myplatform.com",
        )
        parser.add_argument(
            "--fixture", help="Fixture file", default=path.join(path.dirname(path.realpath(__file__)), "fixture.json")
        )

    def replace_platform(self, target_url, source_url):
        """
        replace_platform replaces consumer platform address to edx-platform
        """
        parsed_target_url = urlparse(target_url)
        parsed_source_url = urlparse(source_url)
        return parsed_target_url._replace(netloc=parsed_source_url.netloc, scheme=parsed_source_url.scheme).geturl()

    def handle(self, *args, **options):
        if settings.APP_ENV not in ["DEV", "TESTING"]:
            raise CommandError("Can be used only for TESTING or DEV environments")
        data = json.loads(Path(options["fixture"]).read_text())
        for i, fixture in enumerate(data):
            if fixture["model"] != "lti1p3_tool_config.ltitool":
                continue
            data[i]["fields"]["issuer"] = self.replace_platform(
                fixture["fields"]["issuer"], options["lti-consumer-url"]
            )
            data[i]["fields"]["auth_login_url"] = self.replace_platform(
                fixture["fields"]["auth_login_url"], options["lti-consumer-url"]
            )
            data[i]["fields"]["auth_token_url"] = self.replace_platform(
                fixture["fields"]["auth_token_url"], options["lti-consumer-url"]
            )
            data[i]["fields"]["auth_audience"] = self.replace_platform(
                fixture["fields"]["auth_audience"], options["lti-consumer-url"]
            )
            data[i]["fields"]["key_set_url"] = self.replace_platform(
                fixture["fields"]["key_set_url"], options["lti-consumer-url"]
            )
        with tempfile.NamedTemporaryFile(mode="w", prefix="fixture_vcl_", suffix=".json") as temp:
            temp.write(json.dumps(data))
            call_command("loaddata", path.join(tempfile.gettempdir(), temp.name), format="json")
