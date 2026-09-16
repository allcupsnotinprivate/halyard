"""Runnable demo: an action as a callable unit, and as an MCP tool.

An ``Action`` has one operation, ``execute``. Call the instance to run it
through the policy chain; the same action is auto-exposed as an MCP tool with a
flat input schema. A ``Provider`` is internal infrastructure, wired in as a
dependency and never exposed.

Run:
    uv run python examples/actions.py
"""

import anyio
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams
from pydantic import BaseModel

from warpweft import Action, ActionParams, App, EmptySettings, Provider, Registry
from warpweft.mcp import build_server


class Vocabulary(Provider[EmptySettings]):
    """Internal infrastructure: never an entry point, never a tool."""

    def stopwords(self) -> set[str]:
        return {"the", "a", "an", "of", "to"}


class Summarise(ActionParams):
    text: str
    max_words: int = 20


class Digest(BaseModel):
    summary: str
    words: int


class Summarize(Action[EmptySettings, Summarise, Digest]):
    """Summarise a document by dropping stopwords and clipping length."""

    description = "Summarise a document."
    read_only = True

    vocab: Vocabulary  # dependency: the resolved instance, injected before start

    async def execute(self, params: Summarise) -> Digest:
        stop = self.vocab.stopwords()
        kept = [w for w in params.text.split() if w.lower() not in stop][: params.max_words]
        return Digest(summary=" ".join(kept), words=len(kept))


async def main() -> None:
    registry = Registry()
    registry.register(Vocabulary)
    registry.register(Summarize)
    app = App(registry=registry)

    async with app.run() as container:
        # 1) Call the action as an object - guarded, through its policy chain.
        summarize = await container.get(Summarize)
        digest = await summarize(text="the quick brown fox jumps over a lazy dog", max_words=4)
        print("call summarize(...):", digest)

        # 2) The same action, served as an MCP tool with a flat input schema.
        async with create_client_server_memory_streams() as (client_streams, server_streams):
            server = build_server(app)
            async with anyio.create_task_group() as tg:
                tg.start_soon(
                    lambda: server.run(*server_streams, server.create_initialization_options(), raise_exceptions=True)
                )
                async with ClientSession(*client_streams) as client:
                    await client.initialize()

                    tools = await client.list_tools()
                    for t in tools.tools:  # only the action; the provider is not exposed
                        print(f"tool: {t.name} - {t.description}")
                        print(f"  input : {list(t.input_schema['properties'])}")  # flat: text, max_words

                    result = await client.call_tool("summarize__execute", {"text": "a fox and the dog", "max_words": 3})
                    print("call summarize__execute(...):", result.structured_content)
                tg.cancel_scope.cancel()


if __name__ == "__main__":
    anyio.run(main)
