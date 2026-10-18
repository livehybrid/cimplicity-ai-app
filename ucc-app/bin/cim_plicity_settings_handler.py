"""REST handler for /cim-plicity_settings (restmap [admin_external:cim-plicity_settings]).

Wraps the UCC-generated cim-plicity_rh_settings.py so the field models stay
generated from globalConfig.json, and fixes one thing in it: listing the whole
collection.

splunktaucclib 8.2.0's RestHandler.all() asks the endpoint for the model of
name None (get_encrypted_field_names(None)). For a MultipleModel, which every
UCC settings endpoint is, that raises RestError(404, "name=None"), so
GET .../cim-plicity_settings answered 500 wrapping a 404. Per-stanza GETs (what
the Configuration page makes) never touch that path.

The collection list is therefore built from the per-stanza read the UI already
relies on: one handler.get() per model, which also keeps the same credential
handling (encrypted fields masked unless --cred-- is passed). A stanza that is
not present in the conf is skipped rather than failing the whole list.
"""
import import_declare_test  # noqa: F401  (puts the app's lib/ on sys.path)

import importlib
import logging

from solnlib.utils import is_true
from splunktaucclib.rest_handler import admin_external
from splunktaucclib.rest_handler.admin_external import AdminExternalHandler, make_conf_item
from splunktaucclib.rest_handler.error import RestError

# The module name has a hyphen, so it cannot be imported with a plain import.
endpoint = importlib.import_module("cim-plicity_rh_settings").endpoint


class SettingsHandler(AdminExternalHandler):
    def handleList(self, confInfo):
        if self.callerArgs.id:
            return super().handleList(confInfo)

        decrypt = is_true(self.callerArgs.data.get(self.ACTION_CRED, [False])[0])
        for name in self.endpoint.models:
            try:
                entities = list(self.handler.get(name, decrypt=decrypt))
            except RestError as exc:
                if exc.status == 404:
                    continue
                raise
            for entity in entities:
                make_conf_item(confInfo[entity.name], entity.content, entity.eai)


if __name__ == "__main__":
    logging.getLogger().addHandler(logging.NullHandler())
    admin_external.handle(endpoint, handler=SettingsHandler)
