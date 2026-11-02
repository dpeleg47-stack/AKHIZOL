from aiogram.fsm.state import State, StatesGroup


class OrderFlow(StatesGroup):
    confirming = State()  # пользователь проверяет распознанный список
