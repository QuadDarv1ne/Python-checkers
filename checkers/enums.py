from enum import Enum, auto

class SideType(Enum):
    WHITE = auto()
    BLACK = auto()

    @staticmethod
    def opposite(side):
        if (side == SideType.WHITE):
            return SideType.BLACK
        elif (side == SideType.BLACK):
            return SideType.WHITE
        else: raise ValueError()

class CheckerType(Enum):
    NONE = auto()
    WHITE_REGULAR = auto()
    BLACK_REGULAR = auto()
    WHITE_QUEEN = auto()
    BLACK_QUEEN = auto()

class DifficultyType(Enum):
    EASY = auto()
    MEDIUM = auto()
    HARD = auto()
    GRANDMASTER = auto()

    @property
    def depth(self):
        '''Глубина просчёта ходов для каждого уровня сложности'''
        return {
            DifficultyType.EASY: 1,
            DifficultyType.MEDIUM: 2,
            DifficultyType.HARD: 4,
            DifficultyType.GRANDMASTER: 6
        }[self]

    @property
    def name_ru(self):
        '''Название на русском'''
        return {
            DifficultyType.EASY: "Лёгкий",
            DifficultyType.MEDIUM: "Средний",
            DifficultyType.HARD: "Сложный",
            DifficultyType.GRANDMASTER: "Гроссмейстер"
        }[self]