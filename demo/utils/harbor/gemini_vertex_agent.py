"""Gemini CLI agent for harbor with Vertex AI + ADC credentials.

harbor's stock GeminiCli only injects "Login with Google" oauth_creds.json;
in Vertex mode it forwards env vars but never uploads the ADC file, so the
in-container CLI has no credentials. This subclass uploads the host ADC json
(GOOGLE_APPLICATION_CREDENTIALS on the host, default ~/.config/gcloud/
application_default_credentials.json) into the sandbox and points the CLI at
it, keeping the README contract: vertexai=True, project lucid-clone-504421-a5,
location global (GFS credit billing).

Use:  harbor run -a utils.harbor.gemini_vertex_agent:GeminiVertexCli \
        -m gemini-3.8-flash --ak reasoning_effort=high ...
with GOOGLE_GENAI_USE_VERTEXAI=true GOOGLE_CLOUD_PROJECT=... GOOGLE_CLOUD_LOCATION=global
"""
import os
import shlex
from pathlib import Path, PurePosixPath

from harbor.agents.installed.gemini_cli import GeminiCli

_REMOTE_ADC = PurePosixPath("/tmp/gemini-secrets/adc.json")


class GeminiVertexCli(GeminiCli):
    @staticmethod
    def name() -> str:
        return "gemini-vertex-cli"

    def _adc_path(self) -> Path:
        p = self._get_env("GOOGLE_APPLICATION_CREDENTIALS") or os.path.expanduser(
            "~/.config/gcloud/application_default_credentials.json")
        p = Path(p)
        if not p.is_file():
            raise ValueError(f"ADC file not found: {p}")
        return p

    def _resolve_auth_env(self) -> dict[str, str]:
        env = super()._resolve_auth_env()
        env.update({
            "GOOGLE_GENAI_USE_VERTEXAI": "true",
            "GOOGLE_CLOUD_PROJECT": self._get_env("GOOGLE_CLOUD_PROJECT") or "lucid-clone-504421-a5",
            "GOOGLE_CLOUD_LOCATION": self._get_env("GOOGLE_CLOUD_LOCATION") or "global",
            "GOOGLE_APPLICATION_CREDENTIALS": _REMOTE_ADC.as_posix(),
        })
        env.pop("GEMINI_API_KEY", None)
        return env

    async def _inject_adc(self, environment, env):
        remote_dir = _REMOTE_ADC.parent.as_posix()
        await self.exec_as_root(environment, command=f"mkdir -p {shlex.quote(remote_dir)}")
        await environment.upload_file(self._adc_path(), _REMOTE_ADC.as_posix())
        # readable by the agent user (upload lands as root)
        await self.exec_as_root(environment, command=f"chmod 644 {shlex.quote(_REMOTE_ADC.as_posix())}")
        self.logger.info("Gemini Vertex auth: ADC uploaded to %s", _REMOTE_ADC)

    async def run(self, *args, **kwargs):
        # GeminiCli.run(self, instruction, environment, context)
        environment = kwargs.get("environment") or args[1]
        await self._inject_adc(environment, self._resolve_auth_env())
        return await super().run(*args, **kwargs)
