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
