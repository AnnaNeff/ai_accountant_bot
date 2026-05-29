from aiogram.fsm.state import State, StatesGroup


class AiTransactionConfirmation(StatesGroup):
    waiting_for_confirmation = State()
