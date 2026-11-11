class LapTimeResults:
    """
    Flexible container for lap time simulation results.
    Supports dynamic addition of any result channel or array.
    """

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def keys(self):
        return self.__dict__.keys()

    def as_dict(self):
        return dict(self.__dict__)
