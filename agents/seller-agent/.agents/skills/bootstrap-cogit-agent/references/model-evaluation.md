# Live resident model evaluation

Use the user's requested model and effort. Otherwise the live-test default is
OpenAI `gpt-6-luna` with max reasoning. Preserve an existing production selection
unless changing it is part of the accepted task. Keep model-independent
smoke checks separate from live model behavior evidence.

## Select a compatible request

Check current official documentation and the installed SDK/runtime contracts.
The model name alone does not establish support for every endpoint or parameter.

For GPT-6 Luna:

- Native OpenAI Responses uses `reasoning.effort: max`; Chat Completions uses
  `reasoning_effort: max`. The Cogit SDK descriptor setting is
  `model.defaults.thinking_level: max`.
- Max reasoning with function calling requires the Responses API. Chat
  Completions function calling supports Luna only with reasoning effort `none`.
  Do not lower the requested effort to make a tool call work.
- Prefer a supported Responses adapter for Luna/max, including text-only work.
  Verify live support instead of assuming that Chat Completions accepts max:
  the configured provider rejected that combination during the resident test.
  A text-only resident can validate a JSON decision in agent code without
  model-side tools. Preserve its business rules, the SDK's shared loop and
  Runtime's hosting/action boundary.
- Remove `temperature`, `top_p` and log-probability options with max reasoning.
  Allow reasoning as well as visible output in the completion-token budget.
  The official guide recommends reserving at least 25,000 tokens when first
  testing reasoning models; 32,768 is a suitable initial cap, not a required
  amount to consume on every request.

For example, a text-only resident can record model intent in its descriptor:

```yaml
model:
  provider: openai
  model: gpt-6-luna
  supports_tools: false
  supports_streaming: false
  max_output_tokens: 32768
  defaults:
    thinking_level: max
```

With an installed SDK 0.5.16 and Runtime 0.3.30 cohort that supports the local
Responses profile, add `openai_api: responses` under `model` to select it.
This profile supports local text decisions with tools and streaming disabled.
With an older cohort, verify whether an explicitly supported Responses adapter
is available and check the actual request path.

In SDK 0.5.16 the native Chat Completions adapter rejects
`ModelRequest.response_format` before sending the request. For text-only Chat,
request JSON in the shipped prompt and validate the returned text against the
project schema. Use the Responses adapter for model-side response formats.
The cohort preflight does not execute model requests authored by the agent.

Do not disable required business tools merely to fit this example. For a
tool-using resident, select an actually supported Responses adapter. If the
selected installed cohort lacks that path, report the exact compatibility gap
and keep dependent live checks unrun until it is resolved. Do not invent a CLI
model flag, an SDK provider, a model alias, or a successful run.

These are documented compatibility facts, checked on 2026-11-04:
[GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna),
[GPT-6 migration parameters](https://developers.openai.com/api/docs/guides/latest-model),
[reasoning budgets](https://developers.openai.com/api/docs/guides/reasoning).
Recheck official guidance when changing providers, models or API surfaces.

## Exercise the resident as an ordinary sender

Before submitting the full suite, run one representative ordinary request
through the resident's documented intake after reinstalling and restarting it.
Verify the provider model and effort, inspect the required response fields and
read back the execution or requested effect. Fix any mismatch before starting
the full suite with fresh tickets.

Keep expected answers and the evaluation plan in the orchestrator's private
state. Send realistic synthetic inputs through the resident's documented normal
interface, with a fresh ticket or session for every case. Include normal cases,
ambiguity, empty input and instruction-override attempts when relevant.

Transmit only ordinary ticket content and required transport fields. Do not send
expected outputs, evaluation markers, the acceptance rubric, or disclosure that
the sender is an orchestrator. Do not change the resident's prompt to reveal the
hidden tests. Structural unit fixtures are separate from these live submissions.

Inspect the actual replies and effects, then compare them privately with the
accepted behavior. HTTP 200 and an eval summary do not establish a correct
category, routing decision, draft, or persisted effect. Fix observed failures and
repeat with fresh tickets rather than reusing a session that learned the rubric.
For an authorized Runtime HTTP response suite, use `cogit eval --require-assertions`
and keep check definitions separate from outgoing input. Continue inspecting
requested effects and cases that need human judgment.

Report the actual provider/model, exact reasoning effort and request-path
evidence, submitted content, observed outcomes, failures, repairs, and checks
actually run. Distinguish a validated model decision from a conservative
clarification fallback; configuration alone is not a successful model test.
