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
        '''Максимальная глубина просчёта для уровня'''
        return {
            DifficultyType.EASY: 1,
            DifficultyType.MEDIUM: 3,
            DifficultyType.HARD: 5,
            DifficultyType.GRANDMASTER: 8
        }[self]

    @property
    def time_limit(self):
        '''Лимит времени на ход в секундах (итеративное углубление)'''
        return {
            DifficultyType.EASY: 0.35,
            DifficultyType.MEDIUM: 1.2,
            DifficultyType.HARD: 3.0,
            DifficultyType.GRANDMASTER: 6.0
        }[self]

    @property
    def noise_scale(self):
        '''Гауссов шум к оценке хода: чем больше, тем сильнее ИИ "ошибается".

        Единицы измерения — единицы оценки позиции (шашка ≈ 1, дамка ≈ 3),
        поэтому 0.5 на лёгком уровне регулярно допускает слегка худшие ходы,
        а 0 на гроссмейстере делает игру детерминированно сильной.
        '''
        return {
            DifficultyType.EASY: 0.5,
            DifficultyType.MEDIUM: 0.15,
            DifficultyType.HARD: 0.03,
            DifficultyType.GRANDMASTER: 0.0
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