from checkers.enums import CheckerType

class Checker:
    '''Шашка. __slots__ уменьшает память и ускоряет создание — объект создается на каждой клетке поля.'''

    __slots__ = ('__type',)

    def __init__(self, type: CheckerType = CheckerType.NONE):
        self.__type = type

    @property
    def type(self):
        return self.__type

    def change_type(self, type: CheckerType):
        '''Изменение типа шашки'''
        self.__type = type