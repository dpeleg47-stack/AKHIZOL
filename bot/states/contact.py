from aiogram.fsm.state import State, StatesGroup


class ContactFlow(StatesGroup):
    value = State()
