#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Приложение для расчета площади вместимости штабелей для тар
Правила размещения:
- Тяжелые тары всегда снизу
- Тары с определенными деталями всегда в доступе
- Верхняя полка зарезервирована под пустую тару
"""

from dataclasses import dataclass
from typing import List, Optional
from enum import Enum


class Priority(Enum):
    """Приоритет доступа к таре"""
    LOW = 1
    NORMAL = 2
    HIGH = 3  # Требует быстрого доступа


@dataclass
class Container:
    """Класс для представления тары"""
    id: str
    name: str
    weight: float  # кг
    length: float  # см
    width: float   # см
    height: float  # см
    is_empty: bool = False
    priority_parts: bool = False  # Содержит ли приоритетные детали
    content: str = ""
    
    @property
    def volume(self) -> float:
        """Объем тары в кубических сантиметрах"""
        return self.length * self.width * self.height
    
    @property
    def base_area(self) -> float:
        """Площадь основания в см²"""
        return self.length * self.width
    
    def __repr__(self):
        status = "Пустая" if self.is_empty else f"С деталями ({self.content})"
        priority = " [ПРИОРИТЕТ]" if self.priority_parts else ""
        return f"{self.name} ({status}, {self.weight}кг){priority}"


@dataclass
class Shelf:
    """Класс для представления полки"""
    level: int  # Уровень полки (0 - нижний, выше - верхние)
    max_weight: float  # Максимальная нагрузка в кг
    length: float  # см
    width: float   # см
    height: float  # Высота полки в см
    containers: List[Container] = None
    reserved_for_empty: bool = False
    
    def __post_init__(self):
        if self.containers is None:
            self.containers = []
    
    @property
    def total_area(self) -> float:
        """Общая площадь полки в см²"""
        return self.length * self.width
    
    @property
    def occupied_area(self) -> float:
        """Занятая площадь в см²"""
        return sum(c.base_area for c in self.containers)
    
    @property
    def free_area(self) -> float:
        """Свободная площадь в см²"""
        return self.total_area - self.occupied_area
    
    @property
    def current_weight(self) -> float:
        """Текущий вес на полке в кг"""
        return sum(c.weight for c in self.containers)
    
    @property
    def utilization_percent(self) -> float:
        """Процент использования площади полки"""
        return (self.occupied_area / self.total_area) * 100 if self.total_area > 0 else 0
    
    def can_add_container(self, container: Container) -> bool:
        """Проверка, можно ли добавить тару на полку"""
        # Проверка зарезервированной полки для пустой тары
        if self.reserved_for_empty and not container.is_empty:
            return False
        if not self.reserved_for_empty and container.is_empty:
            return False
            
        # Проверка веса
        if self.current_weight + container.weight > self.max_weight:
            return False
        
        # Проверка площади
        if self.free_area < container.base_area:
            return False
        
        # Проверка высоты
        if container.height > self.height:
            return False
        
        return True
    
    def add_container(self, container: Container) -> bool:
        """Добавить тару на полку"""
        if self.can_add_container(container):
            self.containers.append(container)
            return True
        return False


class StorageStack:
    """Класс для управления штабелем полок"""
    
    def __init__(self, name: str, base_length: float, base_width: float):
        self.name = name
        self.base_length = base_length  # см
        self.base_width = base_width    # см
        self.shelves: List[Shelf] = []
    
    def add_shelf(self, max_weight: float, height: float, reserved_for_empty: bool = False):
        """Добавить полку в штабель"""
        level = len(self.shelves)
        shelf = Shelf(
            level=level,
            max_weight=max_weight,
            length=self.base_length,
            width=self.base_width,
            height=height,
            reserved_for_empty=reserved_for_empty
        )
        self.shelves.append(shelf)
    
    def organize_containers(self, containers: List[Container]):
        """
        Организовать размещение тар по правилам:
        1. Тяжелые тары снизу
        2. Тары с приоритетными деталями в доступе (средние уровни)
        3. Пустые тары на верхней зарезервированной полке
        """
        # Сортировка тар
        empty_containers = [c for c in containers if c.is_empty]
        priority_containers = [c for c in containers if c.priority_parts and not c.is_empty]
        regular_containers = [c for c in containers if not c.is_empty and not c.priority_parts]
        
        # Сортировка по весу (тяжелые первые)
        regular_containers.sort(key=lambda x: x.weight, reverse=True)
        priority_containers.sort(key=lambda x: x.weight, reverse=True)
        
        # Размещение тар
        placement_log = []
        
        # 1. Размещаем тяжелые обычные тары на нижних полках
        for container in regular_containers:
            placed = False
            # Пытаемся разместить на самых нижних доступных полках
            for shelf in sorted(self.shelves, key=lambda s: s.level):
                if not shelf.reserved_for_empty and shelf.add_container(container):
                    placement_log.append(f"✓ {container.name} размещен на полке {shelf.level} (обычная)")
                    placed = True
                    break
            if not placed:
                placement_log.append(f"✗ {container.name} НЕ размещен - недостаточно места")
        
        # 2. Размещаем приоритетные тары на средних/доступных уровнях
        accessible_shelves = [s for s in self.shelves if not s.reserved_for_empty]
        mid_level = len(accessible_shelves) // 2 if accessible_shelves else 0
        
        for container in priority_containers:
            placed = False
            # Пытаемся разместить начиная со среднего уровня
            for shelf in sorted(accessible_shelves, key=lambda s: abs(s.level - mid_level)):
                if shelf.add_container(container):
                    placement_log.append(f"✓ {container.name} размещен на полке {shelf.level} (ПРИОРИТЕТ - в доступе)")
                    placed = True
                    break
            if not placed:
                placement_log.append(f"✗ {container.name} НЕ размещен - недостаточно места")
        
        # 3. Размещаем пустые тары на зарезервированной верхней полке
        for container in empty_containers:
            placed = False
            for shelf in [s for s in self.shelves if s.reserved_for_empty]:
                if shelf.add_container(container):
                    placement_log.append(f"✓ {container.name} размещен на полке {shelf.level} (пустая тара)")
                    placed = True
                    break
            if not placed:
                placement_log.append(f"✗ {container.name} НЕ размещен - недостаточно места")
        
        return placement_log
    
    def get_statistics(self) -> dict:
        """Получить статистику по штабелю"""
        total_area = sum(s.total_area for s in self.shelves)
        occupied_area = sum(s.occupied_area for s in self.shelves)
        total_containers = sum(len(s.containers) for s in self.shelves)
        total_weight = sum(s.current_weight for s in self.shelves)
        
        return {
            'name': self.name,
            'total_shelves': len(self.shelves),
            'total_area_m2': total_area / 10000,  # перевод в м²
            'occupied_area_m2': occupied_area / 10000,
            'free_area_m2': (total_area - occupied_area) / 10000,
            'utilization_percent': (occupied_area / total_area * 100) if total_area > 0 else 0,
            'total_containers': total_containers,
            'total_weight_kg': total_weight
        }
    
    def print_layout(self):
        """Вывести раскладку штабеля"""
        print(f"\n{'='*80}")
        print(f"ШТАБЕЛЬ: {self.name}")
        print(f"Базовые размеры: {self.base_length}см x {self.base_width}см")
        print(f"{'='*80}\n")
        
        for shelf in reversed(self.shelves):  # Сверху вниз для наглядности
            status = "[ПУСТАЯ ТАРА]" if shelf.reserved_for_empty else ""
            print(f"Полка {shelf.level} {status}")
            print(f"  Макс. нагрузка: {shelf.max_weight}кг | Текущий вес: {shelf.current_weight:.1f}кг")
            print(f"  Использование площади: {shelf.utilization_percent:.1f}% ({shelf.occupied_area/10000:.2f}м² из {shelf.total_area/10000:.2f}м²)")
            
            if shelf.containers:
                print(f"  Тары ({len(shelf.containers)}):")
                for container in shelf.containers:
                    print(f"    - {container}")
            else:
                print(f"  Тары: нет")
            print()
    
    def print_statistics(self):
        """Вывести статистику"""
        stats = self.get_statistics()
        print(f"\n{'='*80}")
        print(f"СТАТИСТИКА: {stats['name']}")
        print(f"{'='*80}")
        print(f"Всего полок: {stats['total_shelves']}")
        print(f"Общая площадь: {stats['total_area_m2']:.2f} м²")
        print(f"Занято: {stats['occupied_area_m2']:.2f} м² ({stats['utilization_percent']:.1f}%)")
        print(f"Свободно: {stats['free_area_m2']:.2f} м²")
        print(f"Всего тар: {stats['total_containers']}")
        print(f"Общий вес: {stats['total_weight_kg']:.1f} кг")
        print(f"{'='*80}\n")


def optimize_container_placement(shelf: Shelf, containers: List[Container]) -> List[Container]:
    """
    Оптимизация размещения тар на полке для минимизации свободной площади.
    Использует жадный алгоритм упаковки.
    """
    placed = []
    remaining = containers.copy()
    
    # Сортируем по площади основания (большие первыми)
    remaining.sort(key=lambda c: c.base_area, reverse=True)
    
    for container in remaining:
        if shelf.can_add_container(container):
            shelf.add_container(container)
            placed.append(container)
    
    # Удаляем размещенные тары из списка
    for c in placed:
        remaining.remove(c)
    
    return remaining


def input_float(prompt: str, min_val: float = 0) -> float:
    """Ввод числа с плавающей точкой с валидацией"""
    while True:
        try:
            value = float(input(prompt))
            if value >= min_val:
                return value
            print(f"Значение должно быть >= {min_val}")
        except ValueError:
            print("Ошибка ввода. Введите число.")


def input_int(prompt: str, min_val: int = 0) -> int:
    """Ввод целого числа с валидацией"""
    while True:
        try:
            value = int(input(prompt))
            if value >= min_val:
                return value
            print(f"Значение должно быть >= {min_val}")
        except ValueError:
            print("Ошибка ввода. Введите целое число.")


def input_yes_no(prompt: str) -> bool:
    """Ввод да/нет"""
    while True:
        response = input(prompt + " (да/нет): ").lower().strip()
        if response in ['да', 'yes', 'y', 'д']:
            return True
        elif response in ['нет', 'no', 'n', 'н']:
            return False
        print("Введите 'да' или 'нет'")


def interactive_calculator():
    """Интерактивный калькулятор для расчета штабелей"""
    
    print("=" * 80)
    print("ИНТЕРАКТИВНЫЙ КАЛЬКУЛЯТОР ШТАБЕЛЕЙ ДЛЯ ТАР")
    print("=" * 80)
    print()
    
    # Ввод параметров стеллажа
    print("=== ПАРАМЕТРЫ СТЕЛЛАЖА ===")
    stack_name = input("Название стеллажа [Стеллаж А1]: ").strip() or "Стеллаж А1"
    
    print("\nРазмеры одного этажа стеллажа (в см):")
    length = input_float("  Длина (см): ", 10)
    width = input_float("  Ширина (см): ", 10)
    
    stack = StorageStack(name=stack_name, base_length=length, base_width=width)
    
    # Ввод количества полок
    print("\n=== ПОЛКИ СТЕЛЛАЖА ===")
    num_shelves = input_int("Количество полок (этажей): ", 1)
    
    for i in range(num_shelves):
        print(f"\nПолка {i} ({'верхняя' if i == num_shelves - 1 else 'нижняя' if i == 0 else 'средняя'}):")
        shelf_height = input_float(f"  Высота полки (см) [50]: ", 1) or 50
        max_weight = input_float(f"  Максимальная нагрузка (кг) [{500 - i * 80}]: ", 1)
        if max_weight == 0:
            max_weight = max(100, 500 - i * 80)
        
        # Верхняя полка резервируется для пустой тары
        reserved = (i == num_shelves - 1) if num_shelves > 1 else False
        if reserved:
            print("  [Автоматически зарезервирована для пустой тары]")
        
        stack.add_shelf(max_weight=max_weight, height=shelf_height, reserved_for_empty=reserved)
    
    # Ввод тар
    print("\n=== ВВОД ТАР ===")
    containers = []
    container_count = input_int("Количество тар для размещения: ", 1)
    
    for i in range(container_count):
        print(f"\n--- Тара {i + 1} ---")
        name = input(f"Название [Тара {i + 1}]: ").strip() or f"Тара {i + 1}"
        
        print("Габариты (в см):")
        cont_length = input_float("  Длина (см): ", 1)
        cont_width = input_float("  Ширина (см): ", 1)
        cont_height = input_float("  Высота (см): ", 1)
        
        weight = input_float("Вес (кг): ", 0)
        
        is_empty = input_yes_no("Пустая тара?")
        
        priority_parts = False
        content = ""
        
        if not is_empty:
            priority_parts = input_yes_no("Содержит приоритетные детали (требует доступа)?")
            content = input("Описание содержимого: ").strip()
        
        container = Container(
            id=f"T{i+1:03d}",
            name=name,
            weight=weight,
            length=cont_length,
            width=cont_width,
            height=cont_height,
            is_empty=is_empty,
            priority_parts=priority_parts,
            content=content
        )
        containers.append(container)
    
    # Расчет и вывод результатов
    print("\n" + "=" * 80)
    print("РАСЧЕТ РАЗМЕЩЕНИЯ...")
    print("=" * 80)
    
    # Анализ перед размещением
    total_containers_area = sum(c.base_area for c in containers)
    total_shelves_area = sum(s.total_area for s in stack.shelves)
    
    print(f"\nОбщая площадь всех тар: {total_containers_area/10000:.2f} м²")
    print(f"Общая площадь всех полок: {total_shelves_area/10000:.2f} м²")
    print(f"Коэффициент заполнения: {(total_containers_area/total_shelves_area*100):.1f}%")
    
    if total_containers_area > total_shelves_area:
        print("\n⚠️  ВНИМАНИЕ: Площадь тар превышает площадь полок!")
        print("   Не все тары поместятся на стеллаже.")
    
    print(f"\nВсего тар для размещения: {len(containers)}")
    print(f"  - Тяжелые/обычные: {len([c for c in containers if not c.is_empty and not c.priority_parts])}")
    print(f"  - Приоритетные (требуют доступа): {len([c for c in containers if c.priority_parts])}")
    print(f"  - Пустые: {len([c for c in containers if c.is_empty])}")
    
    # Организуем размещение
    print(f"\n{'='*80}")
    print("ПРОЦЕСС РАЗМЕЩЕНИЯ:")
    print(f"{'='*80}")
    placement_log = stack.organize_containers(containers)
    for log_entry in placement_log:
        print(log_entry)
    
    # Выводим результат
    stack.print_layout()
    stack.print_statistics()
    
    # Рекомендации по оптимизации
    stats = stack.get_statistics()
    print("\n" + "=" * 80)
    print("АНАЛИЗ И РЕКОМЕНДАЦИИ:")
    print("=" * 80)
    
    if stats['utilization_percent'] < 50:
        print("⚠️  Низкое использование площади (<50%)")
        print("   Рекомендация: Рассмотрите уменьшение количества полок")
    elif stats['utilization_percent'] > 90:
        print("✓ Отличное использование площади (>90%)")
    elif stats['utilization_percent'] > 70:
        print("✓ Хорошее использование площади (>70%)")
    
    unplaced = len([log for log in placement_log if "НЕ размещен" in log])
    if unplaced > 0:
        print(f"\n⚠️  {unplaced} тар(ы) не размещены")
        print("   Рекомендации:")
        print("   - Добавьте больше полок")
        print("   - Увеличьте размеры стеллажа")
        print("   - Увеличьте максимальную нагрузку на полки")
    
    print("\nПРАВИЛА РАЗМЕЩЕНИЯ:")
    print("✓ Тяжелые тары размещены на нижних полках")
    print("✓ Тары с приоритетными деталями размещены в легкодоступных местах")
    if num_shelves > 1:
        print("✓ Верхняя полка зарезервирована для пустой тары")


def demo_mode():
    """Демонстрационный режим с примером"""
    
    print("=" * 80)
    print("ДЕМОНСТРАЦИОННЫЙ РЕЖИМ")
    print("=" * 80)
    print()
    
    # Создаем штабель
    stack = StorageStack(name="Штабель А1", base_length=200, base_width=120)  # 200x120 см
    
    # Добавляем полки (снизу вверх)
    stack.add_shelf(max_weight=500, height=50)  # Полка 0 - нижняя, для тяжелых
    stack.add_shelf(max_weight=300, height=50)  # Полка 1
    stack.add_shelf(max_weight=300, height=50)  # Полка 2
    stack.add_shelf(max_weight=200, height=50)  # Полка 3
    stack.add_shelf(max_weight=100, height=50, reserved_for_empty=True)  # Полка 4 - верхняя, для пустой тары
    
    # Создаем тары
    containers = [
        # Тяжелые тары
        Container("T001", "Тара большая №1", weight=80, length=60, width=40, height=45, content="Корпуса двигателей"),
        Container("T002", "Тара большая №2", weight=75, length=60, width=40, height=45, content="Металлические детали"),
        Container("T003", "Тара средняя №1", weight=50, length=50, width=40, height=40, content="Запчасти"),
        
        # Приоритетные тары (требуют доступа)
        Container("T004", "Тара срочная №1", weight=30, length=40, width=30, height=35, 
                  priority_parts=True, content="Срочный заказ А"),
        Container("T005", "Тара срочная №2", weight=25, length=40, width=30, height=35, 
                  priority_parts=True, content="Срочный заказ Б"),
        
        # Обычные тары
        Container("T006", "Тара малая №1", weight=20, length=40, width=30, height=30, content="Мелкие детали"),
        Container("T007", "Тара малая №2", weight=18, length=40, width=30, height=30, content="Электроника"),
        Container("T008", "Тара средняя №2", weight=45, length=50, width=35, height=40, content="Инструменты"),
        
        # Пустые тары
        Container("T009", "Тара пустая №1", weight=5, length=40, width=30, height=30, is_empty=True),
        Container("T010", "Тара пустая №2", weight=6, length=50, width=35, height=35, is_empty=True),
        Container("T011", "Тара пустая №3", weight=4, length=40, width=30, height=30, is_empty=True),
    ]
    
    print(f"\nВсего тар для размещения: {len(containers)}")
    print(f"  - Тяжелые/обычные: {len([c for c in containers if not c.is_empty and not c.priority_parts])}")
    print(f"  - Приоритетные (требуют доступа): {len([c for c in containers if c.priority_parts])}")
    print(f"  - Пустые: {len([c for c in containers if c.is_empty])}")
    
    # Организуем размещение
    print(f"\n{'='*80}")
    print("ПРОЦЕСС РАЗМЕЩЕНИЯ:")
    print(f"{'='*80}")
    placement_log = stack.organize_containers(containers)
    for log_entry in placement_log:
        print(log_entry)
    
    # Выводим результат
    stack.print_layout()
    stack.print_statistics()
    
    # Дополнительная информация
    print("\nПРАВИЛА РАЗМЕЩЕНИЯ:")
    print("✓ Тяжелые тары размещены на нижних полках")
    print("✓ Тары с приоритетными деталями размещены в легкодоступных местах")
    print("✓ Верхняя полка зарезервирована для пустой тары")


def main():
    """Основная функция с выбором режима"""
    
    print("\n" + "=" * 80)
    print("СИСТЕМА РАСЧЕТА ПЛОЩАДИ И ВМЕСТИМОСТИ ШТАБЕЛЕЙ ДЛЯ ТАР")
    print("=" * 80)
    print("\nВыберите режим работы:")
    print("1. Интерактивный калькулятор (ввод своих данных)")
    print("2. Демонстрационный режим (пример с готовыми данными)")
    print()
    
    while True:
        choice = input("Ваш выбор (1 или 2): ").strip()
        if choice == "1":
            interactive_calculator()
            break
        elif choice == "2":
            demo_mode()
            break
        else:
            print("Пожалуйста, введите 1 или 2")


if __name__ == "__main__":
    main()
