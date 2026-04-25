from typing import override

from a2a.helpers import new_text_artifact_update_event
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import TaskState, TaskStatus, TaskStatusUpdateEvent

from bike_spots_agent.agent import BikeSpotAgent


class BikeSpotAgentExecutor(AgentExecutor):
    def __init__(self):
        self.agent = BikeSpotAgent()

    @override
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if not context.message:
            raise Exception("No message provided")

        query = context.get_user_input()
        full_text = ""

        async for event in self.agent.stream(query):
            if event["content"]:
                full_text += event["content"]
            if event["done"]:
                break

        if full_text:
            await event_queue.enqueue_event(
                new_text_artifact_update_event(
                    task_id=context.task_id,
                    context_id=context.context_id,
                    name="response",
                    text=full_text,
                    append=False,
                    last_chunk=True,
                )
            )

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=context.task_id,
                context_id=context.context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
            )
        )

    @override
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise Exception("cancel not supported")
