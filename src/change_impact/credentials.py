"""API credentials stored only in a supported operating-system keychain."""

from __future__ import annotations


class CredentialError(RuntimeError):
    pass


class SystemCredentials:
    service = "change-impact-investigator"
    secure_backends = (
        "keyring.backends.macOS",
        "keyring.backends.Windows",
        "keyring.backends.SecretService",
        "keyring.backends.kwallet",
    )

    def _backend(self):
        try:
            import keyring

            backend = keyring.get_keyring()
            candidates = getattr(backend, "backends", [backend])
            for candidate in candidates:
                if (
                    type(candidate).__module__.startswith(self.secure_backends)
                    and candidate.priority > 0
                ):
                    return candidate
        except Exception:
            pass
        raise CredentialError(
            "A secure system keychain is unavailable. Install the panel extra and unlock your keychain."
        )

    def available(self) -> bool:
        try:
            self._backend()
            return True
        except CredentialError:
            return False

    def get(self, provider: str) -> str | None:
        try:
            return self._backend().get_password(self.service, provider)
        except Exception:
            raise CredentialError(
                "Could not read the provider key. Unlock your system keychain and try again."
            ) from None

    def set(self, provider: str, value: str) -> None:
        try:
            self._backend().set_password(self.service, provider, value)
        except Exception:
            raise CredentialError(
                "Could not save the provider key in the system keychain."
            ) from None

    def delete(self, provider: str) -> None:
        try:
            backend = self._backend()
            if backend.get_password(self.service, provider) is not None:
                backend.delete_password(self.service, provider)
        except Exception:
            raise CredentialError("Could not remove the saved provider key.") from None
