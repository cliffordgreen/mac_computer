"""
Agentic sampling loop that calls the Anthropic API and local implementation of anthropic-defined computer use tools.
"""

import platform
from collections.abc import Callable
from datetime import datetime
from typing import Any, cast
from enum import Enum
import getpass
import time

from anthropic import Anthropic, APIResponse
from anthropic.types import (
    ToolResultBlockParam,
)
from anthropic.types.beta import (
    BetaContentBlock,
    BetaContentBlockParam,
    BetaImageBlockParam,
    BetaMessage,
    BetaMessageParam,
    BetaTextBlockParam,
    BetaToolResultBlockParam,
)

from tools.bash import BashTool
from tools.computer import ComputerTool
from tools.edit import EditTool
from tools.collection import ToolCollection
from tools.base import ToolResult
import json
from pathlib import Path

WORKFLOWS_PATH = Path("workflows.json")


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value

class Sender(StrEnum):
    USER = "user"
    BOT = "assistant"
    TOOL = "tool"


BETA_FLAG = "computer-use-2024-10-22"
DEFAULT_MODEL = "claude-3-5-sonnet-20241022"


SYSTEM_PROMPT = f"""<SYSTEM_CAPABILITY>
* You are utilizing a macOS environment using {platform.machine()} architecture with internet access.
* You can install Mac applications using brew install commands.
* To open Safari or other Mac applications, use the 'open' command.
* GUI applications can be started directly without display settings.
* For keyboard shortcuts, use macOS conventions:
  - Use 'command' (not 'ctrl') for most shortcuts (e.g., command+t for new tab)
  - Common macOS shortcuts: 
    * command+t (new tab)
    * command+n (new window)
    * command+w (close tab/window)
    * command+q (quit application)
    * command+c (copy)
    * command+v (paste)
* When using bash tool with commands that output large quantities of text, redirect into a tmp file and use str_replace_editor or `grep -n -B <lines before> -A <lines after> <query> <filename>` to confirm output.
* When viewing a page it can be helpful to zoom out so that you can see everything on the page. Either that, or make sure you scroll down to see everything before deciding something isn't available.
* When using your computer function calls, they take a while to run and send back to you. Where possible/feasible, try to chain multiple of these calls all into one function calls request.
* The current date is {datetime.today().strftime('%A, %B %-d, %Y')}.
</SYSTEM_CAPABILITY>

<AIRBNB>
How to access tax documents in airbnb 

If a tax document was issued to you, you can get a copy of it in your Airbnb account.

Click on your profile picture and select Account
On the Account page, select Taxes
Under the Taxpayers tab, select the > icon
The Tax documents tab shows a list of tax documents issued to you (up to 4 years)
Alternatively, you can find all tax documents at user account level:

Go to earnings dashboard
Select Taxes information > Tax documents
Note: Go to Tax documents to find a list of all tax documents issued to you over the last 4 years. Refer to the “Your 202X Tax Form(s) Is Ready!” email Airbnb sent, which would've referenced a Form 1099 if you are receiving one.
</AIRBNB>

<ETRADE>
Go to the E*TRADE website and log in to your account.
Select Dccuments 
Then  selection Tax Document 2023 Tax year
Then download allss relevent 1099 forms 
</ETRADE>


<IMPORTANT>
* If the item you are looking at is a pdf, if after taking a single screenshot of the pdf it seems that you want to read the entire document instead of trying to continue to read the pdf from your screenshots + navigation, determine the URL, use curl to download the pdf, install and use pdftotext to convert it to a text file, and then read that text file directly with your StrReplaceEditTool.
</IMPORTANT>"""

# def load_workflows():
#     if WORKFLOWS_PATH.exists():
#         with open(WORKFLOWS_PATH, 'r') as f:
#             return json.load(f)
#     return {}

# def save_workflows(workflows):
#     with open(WORKFLOWS_PATH, 'w') as f:
#         json.dump(workflows, f, indent=2)

tool_collection = ToolCollection(
    ComputerTool(),
    BashTool(),
    EditTool(),
)


# async def sampling_loop(
#     *,
#     model: str = DEFAULT_MODEL,
#     system_prompt_suffix: str,
#     messages: list[BetaMessageParam],
#     output_callback: Callable[[BetaContentBlock], None],
#     tool_output_callback: Callable[[ToolResult, str], None],
#     api_response_callback: Callable[[APIResponse[BetaMessage]], None],
#     api_key: str,
#     only_n_most_recent_images: int | None = None,
#     max_tokens: int = 4096,
# ):
async def sampling_loop(
    *,
    model: str = DEFAULT_MODEL,
    system_prompt_suffix: str,
    messages: list[BetaMessageParam],
    output_callback: Callable[[BetaContentBlock], None],
    tool_output_callback: Callable[[ToolResult, str], None],
    api_response_callback: Callable[[APIResponse[BetaMessage]], None],
    api_key: str,
    only_n_most_recent_images: int | None = None,
    max_tokens: int = 4096,
    task_description: str,  # New parameter
):
    """
    Agentic sampling loop for the assistant/tool interaction of computer use.
    """
    tool_collection = ToolCollection(
        ComputerTool(),
        BashTool(),
        EditTool(),
    )

    downloads_dir = Path.home() / "Downloads"
    start_time = time.time()
    # workflows = load_workflows()
    #     # Check if a workflow exists for the given task
    # if task_description in workflows:
    #     # Execute the saved workflow
    #     saved_workflow = workflows[task_description]
    #     print(f"Executing saved workflow for task: {task_description}")

    #     # Collect parameters if any
    #     parameters = {}
    #     for step in saved_workflow:
    #         if 'parameters' in step:
    #             for param in step['parameters']:
    #                 if param not in parameters:
    #                     if 'password' in param.lower():
    #                         parameters[param] = getpass.getpass(f"Please provide {param}: ")
    #                     else:
    #                         parameters[param] = input(f"Please provide {param}: ")

    #     for step in saved_workflow:
    #         tool_name = step['tool_name']
    #         tool_input = step['tool_input'].copy()

    #         # Replace placeholders with actual values
    #         for key, value in tool_input.items():
    #             if isinstance(value, str) and value.startswith('{') and value.endswith('}'):
    #                 param_name = value.strip('{}')
    #                 tool_input[key] = parameters.get(param_name, value)

    #         result = await tool_collection.run(
    #             name=tool_name,
    #             tool_input=tool_input,
    #         )

    #         # Handle the tool result
    #         tool_output_callback(result, tool_use_id=None)

    #         if result.error:
    #             print(f"Workflow step failed: {result.error}")
    #             # If a step fails, fall back to the standard loop
    #             break
    #     else:
    #         # All steps succeeded, return the messages
    #         return messages

    system = (
        f"{SYSTEM_PROMPT}{' ' + system_prompt_suffix if system_prompt_suffix else ''}"
    )
    # current_workflow_steps = []

    while True:
        if only_n_most_recent_images:
            _maybe_filter_to_n_most_recent_images(messages, only_n_most_recent_images)

        client = Anthropic(api_key=api_key)

        # Call the API
        raw_response = client.beta.messages.with_raw_response.create(
            max_tokens=max_tokens,
            messages=messages,
            model=model,
            system=system,
            tools=tool_collection.to_params(),
            betas=[BETA_FLAG],
        )

        api_response_callback(cast(APIResponse[BetaMessage], raw_response))

        response = raw_response.parse()

        messages.append(
            {
                "role": "assistant",
                "content": cast(list[BetaContentBlockParam], response.content),
            }
        )

        tool_result_content: list[BetaToolResultBlockParam] = []
        # for content_block in cast(list[BetaContentBlock], response.content):
        #     output_callback(content_block)
        #     if content_block.type == "tool_use":
        #         result = await tool_collection.run(
        #             name=content_block.name,
        #             tool_input=cast(dict[str, Any], content_block.input),
        #         )
        #         tool_result_content.append(
        #             _make_api_tool_result(result, content_block.id)
        #         )
        #         tool_output_callback(result, content_block.id)
        for content_block in cast(list[BetaContentBlock], response.content):
            output_callback(content_block)
            if content_block.type == "tool_use":
                result = await tool_collection.run(
                    name=content_block.name,
                    tool_input=cast(dict[str, Any], content_block.input),
                )
                tool_result_content.append(
                    _make_api_tool_result(result, content_block.id)
                )
                tool_output_callback(result, content_block.id)

                # # Record the successful tool use
                # if not result.error:
                #     sanitized_input = content_block.input.copy()
                #     # Parameterize sensitive information
                #     parameters = []
                #     for key in ['password', 'user_id', 'username', 'email']:
                #         if key in sanitized_input:
                #             sanitized_input[key] = f'{{{key}}}'
                #             parameters.append(key)
                #     current_workflow_steps.append({
                #         'tool_name': content_block.name,
                #         'tool_input': sanitized_input,
                #         'parameters': parameters
                #     })
                # else:
                #     # If there is an error, reset the workflow steps
                #     current_workflow_steps = []
                #     break

        # if not tool_result_content:
        #     return messages
        if not tool_result_content:
            # # If the conversation ends successfully, save the workflow
            # recent_files = [
            #     f for f in downloads_dir.glob("*1099*.pdf") 
            #     if f.stat().st_mtime > start_time
            # ]
            # if recent_files:
            return messages
            
            # Check for explicit completion messages
            last_message = response.content[-1] if response.content else None
            if isinstance(last_message, dict) and last_message.get("type") == "text":
                text = last_message.get("text", "").lower()
                if any(phrase in text for phrase in [
                    "has been downloaded",
                    "task has been completed",
                    "successfully downloaded",
                    "file is in the downloads folder",
                    "1099 form has been downloaded",
                    "downloaded",
                    "complete"
                ]):
                    return messages

            if current_workflow_steps:
                workflows[task_description] = current_workflow_steps
                save_workflows(workflows)
                print(f"Workflow saved for task: {task_description}")
                return messages

        messages.append({"content": tool_result_content, "role": "user"})


def _maybe_filter_to_n_most_recent_images(
    messages: list[BetaMessageParam],
    images_to_keep: int,
    min_removal_threshold: int = 10,
):
    """
    With the assumption that images are screenshots that are of diminishing value as
    the conversation progresses, remove all but the final `images_to_keep` tool_result
    images in place, with a chunk of min_removal_threshold to reduce the amount we
    break the implicit prompt cache.
    """
    if images_to_keep is None:
        return messages

    tool_result_blocks = cast(
        list[ToolResultBlockParam],
        [
            item
            for message in messages
            for item in (
                message["content"] if isinstance(message["content"], list) else []
            )
            if isinstance(item, dict) and item.get("type") == "tool_result"
        ],
    )

    total_images = sum(
        1
        for tool_result in tool_result_blocks
        for content in tool_result.get("content", [])
        if isinstance(content, dict) and content.get("type") == "image"
    )

    images_to_remove = total_images - images_to_keep
    # for better cache behavior, we want to remove in chunks
    images_to_remove -= images_to_remove % min_removal_threshold

    for tool_result in tool_result_blocks:
        if isinstance(tool_result.get("content"), list):
            new_content = []
            for content in tool_result.get("content", []):
                if isinstance(content, dict) and content.get("type") == "image":
                    if images_to_remove > 0:
                        images_to_remove -= 1
                        continue
                new_content.append(content)
            tool_result["content"] = new_content


def _make_api_tool_result(
    result: ToolResult, tool_use_id: str
) -> BetaToolResultBlockParam:
    """Convert an agent ToolResult to an API ToolResultBlockParam."""
    tool_result_content: list[BetaTextBlockParam | BetaImageBlockParam] | str = []
    is_error = False
    if result.error:
        is_error = True
        tool_result_content = _maybe_prepend_system_tool_result(result, result.error)
    else:
        if result.output:
            tool_result_content.append(
                {
                    "type": "text",
                    "text": _maybe_prepend_system_tool_result(result, result.output),
                }
            )
        if result.base64_image:
            tool_result_content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": result.base64_image,
                    },
                }
            )
    return {
        "type": "tool_result",
        "content": tool_result_content,
        "tool_use_id": tool_use_id,
        "is_error": is_error,
    }


def _maybe_prepend_system_tool_result(result: ToolResult, result_text: str):
    if result.system:
        result_text = f"<system>{result.system}</system>\n{result_text}"
    return result_text
