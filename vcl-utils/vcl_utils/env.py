import os


class Env:
    @staticmethod
    def list(env, default=None):
        default = default or []
        if value := os.getenv(env):
            return [v.strip() for v in value.split(",")]

        return default

    @staticmethod
    def str(env, default=None):
        default = default or ""
        if value := os.getenv(env):
            return value.strip()

        return default
