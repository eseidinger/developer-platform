from platform_cli.config import ConfigurationError, authentication_source, runtime_config


def test_deployment_credential_environment_is_selected():
    config = runtime_config({
        "PLATFORM_API_URL": "https://platform.example/",
        "PLATFORM_TOKEN_ENDPOINT": "https://identity.example/token",
        "PLATFORM_CLIENT_ID": "client-id",
        "PLATFORM_CLIENT_SECRET": "client-secret",
    })

    assert config.api_url == "https://platform.example"
    assert authentication_source(config) == "deployment-credential-environment"


def test_partial_deployment_credential_environment_fails_closed():
    try:
        runtime_config({"PLATFORM_API_URL": "https://platform.example", "PLATFORM_CLIENT_ID": "client-id"})
    except ConfigurationError as error:
        assert "PLATFORM_CLIENT_SECRET" in str(error)
    else:
        raise AssertionError("expected incomplete credential environment to fail")


def test_access_token_takes_precedence_over_an_incomplete_credential_environment():
    config = runtime_config({
        "PLATFORM_API_URL": "https://platform.example",
        "PLATFORM_ACCESS_TOKEN": "access-token",
        "PLATFORM_CLIENT_ID": "client-id",
    })

    assert authentication_source(config) == "access-token-environment"
