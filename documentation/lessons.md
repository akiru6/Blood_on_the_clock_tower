# Lessons Learned: LangGraph Social Deduction Game (Phase 1)

This document consolidates key findings from the initial development phase, focusing on LangGraph state, Pydantic-AI integration, LLM provider interactions, and debugging strategies.

## 1. LangGraph State vs. `stream()` Output

*   **Core Mechanism:** LangGraph nodes receive the complete current state (`GraphState`) and return a dictionary of *updates*. LangGraph merges these updates internally to create the next complete state passed to the subsequent node. This internal process works reliably.
*   **`stream()` Behavior:** The `graph.stream()` iterator yields `{ node_name: state_dict }` after each node completes. **Observation:** The `state_dict` yielded by `stream()` often primarily contains only the keys explicitly *returned* by the node (the updates), not necessarily the full merged state including persistent keys.
*   **Logging Implication:** Relying solely on the dictionary yielded by `stream()` for observing the complete state after *every* step can be misleading, showing keys as "missing" when they exist in the internal state.
*   **Refined Logging Solution:** Modify **all graph nodes** to return the **entire modified `state` dictionary** instead of just the updates. This ensures the dictionary yielded by `stream()` accurately reflects the complete state after each step, enabling reliable step-by-step logging in the runner script (`game_runner.py`). *(Alternative explored: Using `graph.get_state()` requires checkpointers, adding complexity deemed unnecessary for current logging needs).*

## 2. Pydantic-AI `Agent` API & Structured Output

*   **Structured Output (`result_type`):** To get validated Pydantic objects from the LLM, the desired output schema must be passed via the `result_type` argument during **`Agent` initialization** (`agent = Agent(..., result_type=YourSchema)`).
*   **`Agent.run()` Signature:** The `.run()` (and `.run_sync()`) methods take the main user prompt as the **first positional argument**. They do *not* accept keyword arguments like `output_model`, `output_cls`, `messages` (for the main prompt), or `system_prompt_override` for basic structured output requests. Other arguments like `deps`, `message_history`, `model_settings` are passed via keyword.
*   **Dynamic Schemas:** Since `Agent` is configured with a fixed `result_type` at initialization, handling dynamically changing output schemas (e.g., `VoteDecision`, `SpeechOutput`) requires creating/managing **multiple `Agent` instances**, one for each required `result_type`. An "Agent Factory" or cache (`_create_agent` in `llm_interface.py`) was implemented for this.
*   **Lesson:** Adhere strictly to documented API signatures. Incorrect assumptions about keyword arguments led to significant debugging time.

## 3. LLM Provider & Model Compatibility (OpenRouter Focus)

*   **Tool Use Requirement:** Using `pydantic-ai`'s `result_type` relies on the underlying LLM's **Tool Use / Function Calling** capability. When using OpenRouter, the selected model *must* support this feature. Models like `deepseek/deepseek-v3-base:free` failed because they lacked this capability, resulting in OpenRouter errors.
*   **Metadata/Response Incompatibility:** Even with models supporting tool use, subtle differences in API response formats (especially metadata like timestamps) proxied by gateways like OpenRouter can cause errors in client libraries like `pydantic-ai` that expect a specific format (e.g., the `TypeError: 'NoneType' object cannot be interpreted as an integer` potentially caused by a missing `response.created` field when using certain OpenAI-compatible models via OpenRouter with `result_type` active).
*   **Successful Combination:** `anthropic/claude-3-haiku` via OpenRouter (using `pydantic-ai`'s `OpenAIModel/Provider`) successfully handled `result_type` requests without metadata errors in our tests.
*   **Plain Text as Fallback:** When structured output proved problematic (due to cost, model incompatibility, or library bugs), reverting to **plain text mode** (creating the `Agent` without `result_type`) was a necessary pragmatic step. This required:
    *   Stronger prompt engineering (instructing the LLM to format its string output precisely).
    *   Implementing string parsing logic (e.g., using regex) in the application (`ai_player.py`) to extract needed information.
    *   Accepting that plain text parsing is inherently more fragile than validated structured output.
*   **Lesson:** API gateways add a layer of abstraction. Model capabilities (tool use) and response format compatibility must be verified for the specific gateway + model + client library combination, especially when using advanced features like structured output. Testing different models is often required.

## 4. Proxy Configuration

*   **Challenge:** Direct connections to some LLM providers (Google Gemini) failed with `ConnectTimeout` due to the need for a proxy (Veee+).
*   **Environment Variables:** Standard `HTTP_PROXY`/`HTTPS_PROXY` environment variables, while working for `curl`, were **not reliably picked up** by the Python process/libraries (`httpx`, `pydantic-ai`'s Google provider) in this specific setup.
*   **Explicit Client Configuration (`httpx`):** Attempting to explicitly configure `httpx.AsyncClient` with `proxies=` failed due to a `TypeError`, potentially related to the specific `pydantic-ai` version or incorrect argument usage at the time. (*Note: `httpx` generally DOES accept `proxies=`, so this remains slightly puzzling, possibly version-related.*)
*   **Workaround:** Using **OpenRouter** bypassed the direct connection issue, as connections to `openrouter.ai` succeeded through the proxy without needing explicit configuration within the Python code (likely because OpenRouter's endpoint was less affected by whatever blocked the direct Google connection, or `pydantic-ai`'s `OpenAIProvider` handled proxy env vars differently).
*   **Lesson:** Proxy configuration in Python can be tricky. While environment variables are standard, library support can vary. Explicit client configuration is more robust but requires correct API usage for the specific HTTP client library involved. Using gateways like OpenRouter can sometimes simplify connectivity.

## 5. General Development & Debugging

*   **Async/Sync:** Calling `async` functions from synchronous LangGraph nodes requires explicit handling, typically using `asyncio.run()`. Ensuring the function passed to `asyncio.run()` is *actually* a coroutine is crucial (`get_decision` needed modification).
*   **Dependency Versions:** Version mismatches in core libraries (`pydantic-ai` between `0.0.41` and `0.0.46`) were identified as a likely source of API inconsistencies and bugs. Pinning and comparing dependency versions is vital.
*   **Code Structure:** Simple errors like `NameError` and `UnboundLocalError` arose from refactoring issues where functions/variables were called before definition. Maintaining clear structure and definition order is important.
*   **Incremental Testing & Logging:** Isolating changes and using detailed logging were essential for diagnosing the complex interaction of LangGraph state, `pydantic-ai` calls, LLM responses, and network issues.

## Final Stable Approach Chosen

Based on the journey, the most stable and practical baseline achieved uses:

*   **OpenRouter** (avoids direct Google connection issues).
*   A compatible **free-tier model** (e.g., Mistral 7B Instruct).
*   `pydantic-ai` `Agent` **without `result_type`**.
*   **Plain text** LLM interaction.
*   **Prompt engineering** requesting specific string formats.
*   **String parsing** in `ai_player.py` with **placeholder fallback**.
*   All LangGraph nodes modified to **return the full state** for accurate `stream()` logging in `game_runner.py`.

This provides a functional foundation to build upon, deferring the complexities of guaranteed structured output for future iterations if desired.