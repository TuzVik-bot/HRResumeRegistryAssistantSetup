from app.skills import extract_skills


def test_extract_embedded_skills():
    text = "Embedded C++ engineer, STM32, FreeRTOS, CAN, UART, Git, Linux"
    skills = extract_skills(text)
    assert "c++" in skills["programming_languages"]
    assert "stm32" in skills["embedded_stack"]
    assert "freertos" in skills["embedded_stack"]
    assert "can" in skills["protocols"]
    assert "git" in skills["tools"]
