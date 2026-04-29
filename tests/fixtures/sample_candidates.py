from app.resume_parser import parse_resume_profile


ARBUZOV_CANDIDATE = {
    "full_name": "Арбузов Глеб",
    "vacancy": "программист embedded",
    "row_data": {
        "Фамилия, имя": "Арбузов Глеб",
        "вакансия": "программист embedded",
        "оценка рекрутера": "Пеленг, STM32, ESP32, C, SPI, I2C, UART, CAN, FreeRTOS",
    },
}

ARBUZAU_RESUME_TEXT = """
HLEB ARBUZAU
Embedded Software Engineer
Email: hleb.arbuzau@gmail.com
Company: JSC Peleng
STM32, ESP32, FreeRTOS, FDCAN, CAN, SPI, I2C, UART, C
"""

ARBUZAU_RESUME = {
    "original_filename": "HLEB_ARBUZAU_Embedded_Software_Engineer.pdf",
    "profile": parse_resume_profile(ARBUZAU_RESUME_TEXT, "HLEB_ARBUZAU_Embedded_Software_Engineer.pdf"),
}

CHACHUKHA_CANDIDATE = {
    "full_name": "Чечуха Виталий",
    "vacancy": "программист embedded",
    "row_data": {
        "Фамилия, имя": "Чечуха Виталий",
        "вакансия": "программист embedded",
        "оценка рекрутера": "C/C++, Embedded Linux, BSP, Yocto, U-Boot, drivers, board bring-up",
    },
}

CHACHUKHA_RESUME_TEXT = """
Vitali Chachukha
Embedded Software Engineer
Company: Promwad
C, C++, Embedded Linux, Yocto Project, Yocto, U-Boot, Board Bring-up, Device Drivers, drivers
"""

CHACHUKHA_RESUME = {
    "original_filename": "Vitali_Chachukha_Embedded_Software_Engineer.pdf",
    "profile": parse_resume_profile(CHACHUKHA_RESUME_TEXT, "Vitali_Chachukha_Embedded_Software_Engineer.pdf"),
}
