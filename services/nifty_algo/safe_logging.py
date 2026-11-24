"""Keep traceback locations while withholding arbitrary exception messages.

Provider exceptions can contain tokens, response bodies and recipient details.
Use a fresh exception value without cause/context; retain only its stack and the
original type name. Never pass exception arguments or provider payloads here.
"""


def log_failure(logger, operation, error):
    logger.exception(
        "%s failed (%s); exception details withheld",
        operation,
        type(error).__name__,
        exc_info=(RuntimeError, RuntimeError("Exception details withheld"), error.__traceback__),
    )
