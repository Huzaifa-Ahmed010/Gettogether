import ipaddress
from urllib.parse import parse_qs, urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "GetTogether API"
    environment: str = "development"
    database_url: str = "sqlite:///./gettogether.db"
    secret_key: str = "development-only-change-me"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    trusted_proxy_ips: str = ""
    redis_url: str = ""
    access_token_expire_minutes: int = Field(default=30, gt=0, le=1440)
    email_otp_expire_minutes: int = Field(default=10, gt=0, le=60)
    password_reset_expire_minutes: int = Field(default=15, gt=0, le=60)
    email_otp_resend_seconds: int = Field(default=60, gt=0, le=3600)
    email_otp_max_attempts: int = Field(default=5, gt=0, le=10)
    smtp_host: str = ""
    smtp_port: int = Field(default=587, gt=0, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_starttls: bool = True
    smtp_use_ssl: bool = False
    development_show_email_otp: bool = True
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_production_settings(self):
        if self.environment.lower() == "production":
            if (
                self.secret_key in {
                    "development-only-change-me",
                    "replace-with-at-least-64-random-characters",
                }
                or len(self.secret_key) < 64
            ):
                raise ValueError("Production requires a randomly generated SECRET_KEY of at least 64 characters")
            if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
                raise ValueError("Production requires a persistent database such as PostgreSQL")
            sslmodes = parse_qs(urlsplit(self.database_url).query).get("sslmode", [])
            if len(sslmodes) != 1 or sslmodes[0] not in {"require", "verify-ca", "verify-full"}:
                raise ValueError("Production DATABASE_URL must enable PostgreSQL TLS with sslmode=require or stronger")
            if "*" in self.cors_origin_list:
                raise ValueError("Production CORS origins must be explicitly listed")
            if not self.cors_origin_list or any(not self.is_production_origin(origin) for origin in self.cors_origin_list):
                raise ValueError("Production CORS origins must be deployed HTTPS frontend origins")
            if (
                not self.allowed_host_list
                or "*" in self.allowed_host_list
                or any(host.lower() in {"localhost", "127.0.0.1", "testserver"} for host in self.allowed_host_list)
                or any("/" in host or "://" in host or not host.strip() for host in self.allowed_host_list)
            ):
                raise ValueError("Production requires explicit ALLOWED_HOSTS")
            if (
                not self.trusted_proxy_ip_list
                or "*" in self.trusted_proxy_ip_list
                or not self.trusted_proxy_configuration_is_valid
            ):
                raise ValueError("Production requires explicit TRUSTED_PROXY_IPS; wildcard proxy trust is unsafe")
            if not self.redis_url.startswith("rediss://"):
                raise ValueError("Production requires a TLS-protected REDIS_URL (rediss://)")
            if not self.smtp_host or not self.smtp_from_email:
                raise ValueError("Production requires SMTP_HOST and SMTP_FROM_EMAIL for account verification")
            if self.development_show_email_otp:
                raise ValueError("DEVELOPMENT_SHOW_EMAIL_OTP must be disabled in production")
            if self.smtp_use_ssl and self.smtp_use_starttls:
                raise ValueError("SMTP_USE_SSL and SMTP_USE_STARTTLS cannot both be enabled")
            if not self.smtp_use_ssl and not self.smtp_use_starttls:
                raise ValueError("Production SMTP must use SSL or STARTTLS")
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be configured together")
        if bool(self.smtp_host) != bool(self.smtp_from_email):
            raise ValueError("SMTP_HOST and SMTP_FROM_EMAIL must be configured together")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_host_list(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    @property
    def trusted_proxy_ip_list(self) -> list[str]:
        return [address.strip() for address in self.trusted_proxy_ips.split(",") if address.strip()]

    @property
    def trusted_proxy_configuration_is_valid(self) -> bool:
        try:
            for address in self.trusted_proxy_ip_list:
                network = ipaddress.ip_network(address, strict=False)
                minimum_prefix = 16 if network.version == 4 else 48
                if network.prefixlen < minimum_prefix:
                    return False
        except ValueError:
            return False
        return True

    @staticmethod
    def is_production_origin(origin: str) -> bool:
        parsed = urlsplit(origin)
        try:
            parsed.port
            return (
                parsed.scheme == "https"
                and bool(parsed.hostname)
                and not parsed.username
                and not parsed.password
                and parsed.path == ""
                and parsed.query == ""
                and parsed.fragment == ""
                and parsed.hostname.lower() not in {"localhost", "127.0.0.1", "::1"}
            )
        except ValueError:
            return False

settings = Settings()
