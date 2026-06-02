from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def ai_transaction_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Save transaction",
                    callback_data="ai_transaction:save",
                ),
                InlineKeyboardButton(
                    text="Cancel",
                    callback_data="ai_transaction:cancel",
                ),
            ],
        ],
    )


def document_transaction_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Save transaction",
                    callback_data="document_transaction:save",
                ),
                InlineKeyboardButton(
                    text="Cancel",
                    callback_data="document_transaction:cancel",
                ),
            ],
        ],
    )
