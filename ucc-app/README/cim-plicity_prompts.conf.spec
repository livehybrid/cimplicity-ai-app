# cim-plicity_prompts.conf.spec
#
# Prompt guidance for CIMPlicity AI's LLM calls. Place overrides in
# local/cim-plicity_prompts.conf; default/ is replaced on app upgrade.

[<prompt_name>]
* One stanza per LLM call. Recognised names are "ai_detection" and "cim_mapping";
* any other stanza is ignored.

guidance = <string>
* The domain instructions sent to the model, minus the output contract.
* The app always appends its own JSON output contract, which is not configurable,
* because every downstream parser depends on that exact shape.
* Placeholders are substituted by name; every other brace is left untouched, so
* example JSON can be pasted in safely.
* Required placeholders per stanza:
*   ai_detection: {sample_data}. Optional: {description_block}.
*   cim_mapping:  {cim_model}, {available_cim_fields}, {extracted_fields}.
* A value missing a required placeholder is ignored in favour of the shipped
* default, and the reason is logged to cim-plicity.log.
* Default: the guidance shipped in default/cim-plicity_prompts.conf.
