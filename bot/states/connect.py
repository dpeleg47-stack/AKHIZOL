from aiogram.fsm.state import State, StatesGroup


class ConnectFlow(StatesGroup):
    login = State()
    password = State()
