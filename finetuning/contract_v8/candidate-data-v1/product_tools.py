"""Desktop product tool extensions, shared by the UI and dataset contract."""


def register(runtime):
    from verified_copy import register as register_verified_copy
    register_verified_copy(runtime)
