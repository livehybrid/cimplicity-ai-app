
import import_declare_test

from splunktaucclib.rest_handler.endpoint import (
    field,
    validator,
    RestModel,
    MultipleModel,
)
from splunktaucclib.rest_handler import admin_external, util
from splunktaucclib.rest_handler.admin_external import AdminExternalHandler
import logging

util.remove_http_proxy_env_vars()


fields_ai_configuration = [
    field.RestField(
        'api_endpoint',
        required=True,
        encrypted=False,
        default=None,
        validator=validator.String(
            max_len=255, 
            min_len=1, 
        )
    ), 
    field.RestField(
        'api_key',
        required=True,
        encrypted=True,
        default=None,
        validator=validator.String(
            max_len=255, 
            min_len=1, 
        )
    ), 
    field.RestField(
        'model',
        required=True,
        encrypted=False,
        default=None,
        validator=validator.String(
            max_len=50, 
            min_len=1, 
        )
    ), 
    field.RestField(
        'pii_detectors',
        required=False,
        encrypted=False,
        default=None,
        validator=None
    )
]
model_ai_configuration = RestModel(fields_ai_configuration, name='ai_configuration')


fields_logging = [
    field.RestField(
        'loglevel',
        required=True,
        encrypted=False,
        default='INFO',
        validator=validator.Pattern(
            regex=r"""^DEBUG|INFO|WARNING|ERROR|CRITICAL$""", 
        )
    )
]
model_logging = RestModel(fields_logging, name='logging')


endpoint = MultipleModel(
    'cim-plicity_settings',
    models=[
        model_ai_configuration, 
        model_logging
    ],
    need_reload=False,
)


if __name__ == '__main__':
    logging.getLogger().addHandler(logging.NullHandler())
    admin_external.handle(
        endpoint,
        handler=AdminExternalHandler,
    )
