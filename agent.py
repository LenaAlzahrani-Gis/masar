from anthropic import Anthropic
from dotenv import load_dotenv
import tools

load_dotenv()
client = Anthropic()
MODEL = 'claude-sonnet-5-5'

SYSTEM = '''You are a GIS assistant. Solve the request ONLY by calling the provided tools, one step at a time.
Call layers_info first if unsure which layers exist.
Give every output layer a short descriptive English name.
For requests like "nearest ... to me", use nearest_to_point with the user location given in the message, and use the exact layer names from layers_info.
nearest_to_point returns approximate driving distance (road_km) and driving time (minutes) without live traffic. Report them as approximate (use the word تقريباً). If routing is "straight_line", say only straight-line distances are available right now.
If the request is ambiguous, ask ONE clarifying question instead of guessing.
If the request depends on the user location and none is given, tell the user in Arabic to allow location access in the browser or set it from the side panel.
The final answer must be short, simple Arabic. Do not mention tool names, layer names, coordinates or other technical details.'''


def run_agent(user_request, max_steps=8, location=None):
    content = user_request
    if location:
        content += (f'\n\n[User location: lat={location[0]:.5f}, lon={location[1]:.5f}. '
                    'Use it for requests like "near me" or "my location".]')
    else:
        content += '\n\n[No user location has been set.]'
    messages = [{'role': 'user', 'content': content}]
    log = []
    for _ in range(max_steps):
        response = client.messages.create(
            model=MODEL, max_tokens=1000, system=SYSTEM,
            tools=tools.TOOL_SCHEMAS, messages=messages)
        messages.append({'role': 'assistant', 'content': response.content})
        if response.stop_reason != 'tool_use':
            text = ''.join(b.text for b in response.content if b.type == 'text')
            return text, log
        results = []
        for block in response.content:
            if block.type == 'tool_use':
                try:
                    output = tools.TOOL_FUNCS[block.name](**block.input)
                except Exception as e:
                    output = 'error: ' + str(e)
                log.append({'tool': block.name, 'args': block.input, 'result': output})
                results.append({'type': 'tool_result', 'tool_use_id': block.id, 'content': str(output)})
        messages.append({'role': 'user', 'content': results})
    return 'وصلت للحد الأقصى من الخطوات.', log