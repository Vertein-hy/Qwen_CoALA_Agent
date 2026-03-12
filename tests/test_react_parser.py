from core.react_parser import ReActParser


def test_parse_action():
    text = """Thought: use tool\nAction: read_file\nAction Input: notes.txt\n"""
    action = ReActParser.parse_action(text)
    assert action is not None
    assert action.tool_name == "read_file"
    assert action.tool_input == "notes.txt"


def test_parse_final_answer():
    text = "Thought: done\nFinal Answer: result"
    assert ReActParser.parse_final_answer(text) == "result"


def test_parse_action_stops_before_final_answer():
    text = (
        "Thought: use tool\n"
        "Action: python_repl\n"
        "Action Input: print('ok')\n"
        "Final Answer: should not be swallowed\n"
    )
    action = ReActParser.parse_action(text)
    assert action is not None
    assert action.tool_name == "python_repl"
    assert action.tool_input == "print('ok')"
