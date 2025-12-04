#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Streamlit приложение для расчета площади вместимости штабелей для тар
с визуализацией и динамическим управлением буфером пустых тар
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from enum import Enum
import pandas as pd
from datetime import datetime
import json
import io
import copy


class Priority(Enum):
    """Приоритет доступа к таре"""
    LOW = 1
    NORMAL = 2
    HIGH = 3


@dataclass
class Container:
    """Класс для представления тары/коробки"""
    id: str
    name: str
    weight: float  # кг
    length: float  # см
    width: float   # см
    height: float  # см
    is_empty: bool = False
    priority_parts: bool = False
    content: str = ""
    shelf_level: Optional[int] = None
    post_number: Optional[str] = None  # Номер поста
    material: Optional[str] = None  # Материал внутри коробки
    
    @property
    def volume(self) -> float:
        """Объем тары в кубических сантиметрах"""
        return self.length * self.width * self.height
    
    @property
    def base_area(self) -> float:
        """Площадь основания в см²"""
        return self.length * self.width


@dataclass
class Post:
    """Класс для представления поста (заказа)"""
    post_number: str
    containers: List[Container] = field(default_factory=list)
    required_stacks: int = 0
    optimal_shelf_height: float = 0.0
    
    def calculate_requirements(self, base_length: float, base_width: float):
        """Рассчитать требования к стеллажам для поста"""
        if not self.containers:
            return
        
        # Определяем максимальную высоту коробок + запас 15-20см
        max_container_height = max(c.height for c in self.containers)
        self.optimal_shelf_height = max_container_height + 17.5  # средний запас 17.5см
        
        # Группируем коробки по материалам
        materials = {}
        for container in self.containers:
            material = container.material or "unknown"
            if material not in materials:
                materials[material] = []
            materials[material].append(container)
        
        # Рассчитываем необходимое количество стеллажей
        # Учитываем, что коробки с одним материалом должны стоять рядом
        total_length_needed = 0
        
        for material, containers_list in materials.items():
            # Сортируем по весу (тяжелые вниз)
            containers_list.sort(key=lambda x: x.weight, reverse=True)
            
            # Рассчитываем длину для этого материала
            material_length = 0
            current_row_length = 0
            
            for container in containers_list:
                if current_row_length + container.length + 6 > base_length:  # 6см = отступы
                    material_length = max(material_length, current_row_length)
                    current_row_length = container.length
                else:
                    current_row_length += container.length + 3
            
            material_length = max(material_length, current_row_length)
            total_length_needed += material_length + 10  # 10см между группами материалов
        
        # Количество стеллажей = ceil(total_length / base_length)
        self.required_stacks = max(1, int((total_length_needed + base_length - 1) // base_length))
    
    def __repr__(self):
        status = "Пустая" if self.is_empty else f"С деталями"
        priority = " [ПРИОРИТЕТ]" if self.priority_parts else ""
        return f"{self.name} ({status}, {self.weight}кг){priority}"


@dataclass
class Shelf:
    """Класс для представления полки"""
    level: int
    max_weight: float
    length: float
    width: float
    height: float
    containers: List[Container] = field(default_factory=list)
    reserved_for_empty: bool = False
    
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
        """Проверка, можно ли добавить тару на полку с учетом реального размещения"""
        if self.reserved_for_empty and not container.is_empty:
            return False
        if not self.reserved_for_empty and container.is_empty:
            return False
        if self.current_weight + container.weight > self.max_weight:
            return False
        if container.height > self.height:
            return False
        
        # Проверяем реальное размещение (симулируем алгоритм размещения)
        x_offset = 5
        z_offset = 5
        current_row_max_width = 0
        
        # Проходим по уже размещенным тарам
        for existing_container in self.containers:
            if x_offset + existing_container.length > self.length - 5:
                # Переход на новый ряд
                x_offset = 5
                z_offset += current_row_max_width + 3
                current_row_max_width = 0
            
            x_offset += existing_container.length + 3
            current_row_max_width = max(current_row_max_width, existing_container.width)
        
        # Проверяем, влезет ли новая тара
        if x_offset + container.length > self.length - 5:
            # Нужен новый ряд
            x_offset = 5
            z_offset += current_row_max_width + 3
        
        # Проверяем размещение
        if z_offset + container.width > self.width - 5:
            return False  # Не влезает по ширине
        if x_offset + container.length > self.length - 5:
            return False  # Не влезает по длине даже в новом ряду
        
        return True
    
    def add_container(self, container: Container) -> bool:
        """Добавить тару на полку"""
        if self.can_add_container(container):
            self.containers.append(container)
            container.shelf_level = self.level
            return True
        return False
    
    def remove_container(self, container: Container) -> bool:
        """Удалить тару с полки"""
        if container in self.containers:
            self.containers.remove(container)
            container.shelf_level = None
            return True
        return False


class StorageStack:
    """Класс для управления штабелем полок с динамическим буфером"""
    
    def __init__(self, name: str, base_length: float, base_width: float):
        self.name = name
        self.base_length = base_length
        self.base_width = base_width
        self.shelves: List[Shelf] = []
        self.empty_buffer: List[Container] = []  # Буфер пустых тар
        self.history: List[Dict] = []
    
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
    
    def get_empty_shelf(self) -> Optional[Shelf]:
        """Получить полку для пустых тар (верхняя зарезервированная)"""
        for shelf in reversed(self.shelves):
            if shelf.reserved_for_empty:
                return shelf
        return None
    
    def mark_container_empty(self, container: Container):
        """
        Пометить тару как пустую и переместить в буфер (на верх)
        """
        if container.is_empty:
            return
        
        # Находим текущую полку тары
        current_shelf = None
        for shelf in self.shelves:
            if container in shelf.containers:
                current_shelf = shelf
                break
        
        if current_shelf:
            # Удаляем с текущей полки
            current_shelf.remove_container(container)
            
            # Помечаем как пустую
            container.is_empty = True
            container.content = ""
            container.priority_parts = False
            
            # Добавляем в буфер и пытаемся разместить на верхней полке
            self.empty_buffer.append(container)
            
            empty_shelf = self.get_empty_shelf()
            if empty_shelf and empty_shelf.can_add_container(container):
                empty_shelf.add_container(container)
                self.empty_buffer.remove(container)
                
                self.history.append({
                    'timestamp': datetime.now(),
                    'action': 'move_to_buffer',
                    'container': container.name,
                    'from_level': current_shelf.level,
                    'to_level': empty_shelf.level
                })
    
    def organize_containers(self, containers: List[Container]):
        """Организовать размещение тар по правилам"""
        empty_containers = [c for c in containers if c.is_empty]
        priority_containers = [c for c in containers if c.priority_parts and not c.is_empty]
        regular_containers = [c for c in containers if not c.is_empty and not c.priority_parts]
        
        # Сортировка по весу
        regular_containers.sort(key=lambda x: x.weight, reverse=True)
        priority_containers.sort(key=lambda x: x.weight, reverse=True)
        
        placement_log = []
        
        # 1. Размещаем тяжелые обычные тары на нижних полках
        for container in regular_containers:
            placed = False
            for shelf in sorted(self.shelves, key=lambda s: s.level):
                if not shelf.reserved_for_empty and shelf.add_container(container):
                    placement_log.append({
                        'container': container.name,
                        'status': 'placed',
                        'level': shelf.level,
                        'type': 'regular',
                        'weight': container.weight
                    })
                    placed = True
                    break
            if not placed:
                placement_log.append({
                    'container': container.name,
                    'status': 'not_placed',
                    'type': 'regular',
                    'weight': container.weight
                })
        
        # 2. Размещаем приоритетные тары МИНИМУМ на 3-й полке (индекс 2)
        # Фильтруем полки: только с индексом >= 2 и не зарезервированные
        priority_shelves = [s for s in self.shelves if s.level >= 2 and not s.reserved_for_empty]
        
        for container in priority_containers:
            placed = False
            # Сортируем по уровню (начиная с 3-й полки)
            for shelf in sorted(priority_shelves, key=lambda s: s.level):
                if shelf.add_container(container):
                    placement_log.append({
                        'container': container.name,
                        'status': 'placed',
                        'level': shelf.level,
                        'type': 'priority',
                        'weight': container.weight
                    })
                    placed = True
                    break
            if not placed:
                placement_log.append({
                    'container': container.name,
                    'status': 'not_placed',
                    'type': 'priority',
                    'weight': container.weight,
                    'reason': 'Нет доступных полок на уровне 3+ для приоритетных тар'
                })
        
        # 3. Размещаем пустые тары на зарезервированной верхней полке
        for container in empty_containers:
            placed = False
            for shelf in [s for s in self.shelves if s.reserved_for_empty]:
                if shelf.add_container(container):
                    self.empty_buffer.append(container)
                    placement_log.append({
                        'container': container.name,
                        'status': 'placed',
                        'level': shelf.level,
                        'type': 'empty',
                        'weight': container.weight
                    })
                    placed = True
                    break
            if not placed:
                placement_log.append({
                    'container': container.name,
                    'status': 'not_placed',
                    'type': 'empty',
                    'weight': container.weight
                })
        
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
            'total_area_m2': total_area / 10000,
            'occupied_area_m2': occupied_area / 10000,
            'free_area_m2': (total_area - occupied_area) / 10000,
            'utilization_percent': (occupied_area / total_area * 100) if total_area > 0 else 0,
            'total_containers': total_containers,
            'total_weight_kg': total_weight,
            'empty_buffer_count': len(self.empty_buffer)
        }


class Warehouse:
    """Класс для управления несколькими стеллажами и оптимального распределения тар"""
    
    def __init__(self, name: str):
        self.name = name
        self.stacks: List[StorageStack] = []
        self.unplaced_containers: List[Container] = []
    
    def add_stack(self, stack: StorageStack):
        """Добавить стеллаж в склад"""
        self.stacks.append(stack)
    
    def distribute_containers(self, containers: List[Container]) -> Dict:
        """
        Распределить тары по стеллажам для максимальной эффективности
        Возвращает статистику распределения
        """
        # Разделяем тары по типам
        empty_containers = [c for c in containers if c.is_empty]
        priority_containers = [c for c in containers if c.priority_parts and not c.is_empty]
        regular_containers = [c for c in containers if not c.is_empty and not c.priority_parts]
        
        # Сортировка по весу (тяжелые первые)
        regular_containers.sort(key=lambda x: x.weight, reverse=True)
        priority_containers.sort(key=lambda x: x.weight, reverse=True)
        
        placement_stats = {
            'total_containers': len(containers),
            'placed': 0,
            'not_placed': 0,
            'by_stack': {},
            'by_type': {'regular': 0, 'priority': 0, 'empty': 0},
            'placement_log': []
        }
        
        self.unplaced_containers = []
        
        # 1. Размещаем обычные тары (тяжелые на нижние полки)
        for container in regular_containers:
            placed = False
            # Пробуем разместить на доступных стеллажах
            for stack in self.stacks:
                # Доступные полки (не зарезервированные для пустых)
                available_shelves = [s for s in stack.shelves if not s.reserved_for_empty]
                # Сортируем по уровню (снизу вверх)
                for shelf in sorted(available_shelves, key=lambda s: s.level):
                    if shelf.add_container(container):
                        placed = True
                        placement_stats['placed'] += 1
                        placement_stats['by_type']['regular'] += 1
                        
                        if stack.name not in placement_stats['by_stack']:
                            placement_stats['by_stack'][stack.name] = 0
                        placement_stats['by_stack'][stack.name] += 1
                        
                        placement_stats['placement_log'].append({
                            'container': container.name,
                            'stack': stack.name,
                            'shelf': shelf.level,
                            'type': 'regular'
                        })
                        break
                if placed:
                    break
            
            if not placed:
                self.unplaced_containers.append(container)
                placement_stats['not_placed'] += 1
        
        # 2. Размещаем приоритетные тары (минимум 3-я полка)
        for container in priority_containers:
            placed = False
            for stack in self.stacks:
                # Только полки уровня >= 2 (3-я полка и выше)
                priority_shelves = [s for s in stack.shelves if s.level >= 2 and not s.reserved_for_empty]
                for shelf in sorted(priority_shelves, key=lambda s: s.level):
                    if shelf.add_container(container):
                        placed = True
                        placement_stats['placed'] += 1
                        placement_stats['by_type']['priority'] += 1
                        
                        if stack.name not in placement_stats['by_stack']:
                            placement_stats['by_stack'][stack.name] = 0
                        placement_stats['by_stack'][stack.name] += 1
                        
                        placement_stats['placement_log'].append({
                            'container': container.name,
                            'stack': stack.name,
                            'shelf': shelf.level,
                            'type': 'priority'
                        })
                        break
                if placed:
                    break
            
            if not placed:
                self.unplaced_containers.append(container)
                placement_stats['not_placed'] += 1
        
        # 3. Размещаем пустые тары (только зарезервированные полки)
        for container in empty_containers:
            placed = False
            for stack in self.stacks:
                empty_shelves = [s for s in stack.shelves if s.reserved_for_empty]
                for shelf in empty_shelves:
                    if shelf.add_container(container):
                        placed = True
                        placement_stats['placed'] += 1
                        placement_stats['by_type']['empty'] += 1
                        
                        if stack.name not in placement_stats['by_stack']:
                            placement_stats['by_stack'][stack.name] = 0
                        placement_stats['by_stack'][stack.name] += 1
                        
                        placement_stats['placement_log'].append({
                            'container': container.name,
                            'stack': stack.name,
                            'shelf': shelf.level,
                            'type': 'empty'
                        })
                        break
                if placed:
                    break
            
            if not placed:
                self.unplaced_containers.append(container)
                placement_stats['not_placed'] += 1
        
        return placement_stats
    
    def get_total_statistics(self) -> Dict:
        """Получить общую статистику по всем стеллажам"""
        total_stats = {
            'warehouse_name': self.name,
            'total_stacks': len(self.stacks),
            'total_shelves': 0,
            'total_area_m2': 0,
            'occupied_area_m2': 0,
            'total_containers': 0,
            'total_weight_kg': 0,
            'utilization_percent': 0,
            'unplaced_containers': len(self.unplaced_containers),
            'stacks_stats': []
        }
        
        for stack in self.stacks:
            stack_stats = stack.get_statistics()
            total_stats['total_shelves'] += stack_stats['total_shelves']
            total_stats['total_area_m2'] += stack_stats['total_area_m2']
            total_stats['occupied_area_m2'] += stack_stats['occupied_area_m2']
            total_stats['total_containers'] += stack_stats['total_containers']
            total_stats['total_weight_kg'] += stack_stats['total_weight_kg']
            total_stats['stacks_stats'].append(stack_stats)
        
        if total_stats['total_area_m2'] > 0:
            total_stats['utilization_percent'] = (
                total_stats['occupied_area_m2'] / total_stats['total_area_m2'] * 100
            )
        
        return total_stats


def create_3d_visualization(stack: StorageStack):
    """Создать 3D визуализацию штабеля с правильными координатами"""
    fig = go.Figure()
    
    colors = {
        'regular': '#4169E1',      # Royal Blue
        'priority': '#FF8C00',     # Dark Orange
        'empty': '#D3D3D3',        # Light Gray
        'shelf': '#2F4F4F'         # Dark Slate Gray
    }
    
    # Сначала рисуем каркас стеллажа
    shelf_height_cumulative = 0
    
    for shelf in stack.shelves:
        # Рисуем полку как тонкую платформу
        shelf_thickness = 2
        
        # Полка - прямоугольная платформа
        x_shelf = [0, stack.base_length, stack.base_length, 0, 0]
        y_shelf = [shelf_height_cumulative] * 5
        z_shelf = [0, 0, stack.base_width, stack.base_width, 0]
        
        fig.add_trace(go.Scatter3d(
            x=x_shelf,
            y=y_shelf,
            z=z_shelf,
            mode='lines',
            line=dict(color='gray', width=3),
            name=f'Полка {shelf.level}' + (' [БУФЕР]' if shelf.reserved_for_empty else ''),
            showlegend=True,
            hovertext=f'Полка {shelf.level}<br>Макс. нагрузка: {shelf.max_weight}кг<br>Использование: {shelf.utilization_percent:.1f}%',
            hoverinfo='text'
        ))
        
        # Рисуем тары на этой полке с правильным размещением
        x_offset = 5  # Отступ от края
        z_offset = 5
        current_row_max_width = 0  # Максимальная ширина в текущем ряду
        
        for idx, container in enumerate(shelf.containers):
            # Проверяем, влезает ли тара по длине (с учетом отступа)
            if x_offset + container.length > stack.base_length - 5:
                # Переходим на новый ряд
                x_offset = 5
                z_offset += current_row_max_width + 3  # Отступ между рядами
                current_row_max_width = 0
            
            # Проверяем, влезает ли по ширине
            if z_offset + container.width > stack.base_width - 5:
                # Полка переполнена, пропускаем остальные
                break
            
            # Определяем цвет
            if container.is_empty:
                color = colors['empty']
                type_name = 'Пустая'
            elif container.priority_parts:
                color = colors['priority']
                type_name = 'Приоритет'
            else:
                color = colors['regular']
                type_name = 'Обычная'
            
            # Координаты тары (параллелепипед)
            x_min, x_max = x_offset, x_offset + container.length
            y_min = shelf_height_cumulative + shelf_thickness
            y_max = y_min + container.height
            z_min, z_max = z_offset, z_offset + container.width
            
            # 8 вершин параллелепипеда
            vertices = [
                [x_min, y_min, z_min],  # 0: нижний передний левый
                [x_max, y_min, z_min],  # 1: нижний передний правый
                [x_max, y_min, z_max],  # 2: нижний задний правый
                [x_min, y_min, z_max],  # 3: нижний задний левый
                [x_min, y_max, z_min],  # 4: верхний передний левый
                [x_max, y_max, z_min],  # 5: верхний передний правый
                [x_max, y_max, z_max],  # 6: верхний задний правый
                [x_min, y_max, z_max],  # 7: верхний задний левый
            ]
            
            vertices_x = [v[0] for v in vertices]
            vertices_y = [v[1] for v in vertices]
            vertices_z = [v[2] for v in vertices]
            
            # 12 треугольников для 6 граней
            faces = [
                [0, 1, 2], [0, 2, 3],  # Низ (y_min)
                [4, 5, 6], [4, 6, 7],  # Верх (y_max)
                [0, 1, 5], [0, 5, 4],  # Передняя (z_min)
                [2, 3, 7], [2, 7, 6],  # Задняя (z_max)
                [0, 3, 7], [0, 7, 4],  # Левая (x_min)
                [1, 2, 6], [1, 6, 5],  # Правая (x_max)
            ]
            
            i = [f[0] for f in faces]
            j = [f[1] for f in faces]
            k = [f[2] for f in faces]
            
            # Добавляем тару как 3D mesh
            fig.add_trace(go.Mesh3d(
                x=vertices_x,
                y=vertices_y,
                z=vertices_z,
                i=i, j=j, k=k,
                color=color,
                opacity=0.85,
                name=f'{container.name}',
                text=f'{container.name}<br>Тип: {type_name}<br>Вес: {container.weight}кг<br>Размер: {container.length}×{container.width}×{container.height}см<br>Полка: {shelf.level}',
                hoverinfo='text',
                showlegend=False
            ))
            
            # Добавляем контур тары для четкости
            edges = [
                [0, 1], [1, 2], [2, 3], [3, 0],  # Нижнее основание
                [4, 5], [5, 6], [6, 7], [7, 4],  # Верхнее основание
                [0, 4], [1, 5], [2, 6], [3, 7],  # Вертикальные ребра
            ]
            
            for edge in edges:
                edge_x = [vertices_x[edge[0]], vertices_x[edge[1]]]
                edge_y = [vertices_y[edge[0]], vertices_y[edge[1]]]
                edge_z = [vertices_z[edge[0]], vertices_z[edge[1]]]
                
                fig.add_trace(go.Scatter3d(
                    x=edge_x,
                    y=edge_y,
                    z=edge_z,
                    mode='lines',
                    line=dict(color='black', width=2),
                    showlegend=False,
                    hoverinfo='skip'
                ))
            
            # Обновляем смещение для следующей тары
            x_offset += container.length + 3  # Отступ между тарами в ряду
            current_row_max_width = max(current_row_max_width, container.width)  # Запоминаем максимальную ширину в ряду
        
        # Переходим к следующей полке
        shelf_height_cumulative += shelf.height
    
    # Рисуем каркас стеллажа (вертикальные стойки)
    total_height = sum(s.height for s in stack.shelves)
    
    # 4 вертикальные стойки по углам
    corners = [
        [0, 0], [stack.base_length, 0], 
        [stack.base_length, stack.base_width], [0, stack.base_width]
    ]
    
    for corner in corners:
        fig.add_trace(go.Scatter3d(
            x=[corner[0], corner[0]],
            y=[0, total_height],
            z=[corner[1], corner[1]],
            mode='lines',
            line=dict(color='darkgray', width=5),
            showlegend=False,
            hoverinfo='skip'
        ))
    
    # Настройка осей и внешнего вида
    fig.update_layout(
        scene=dict(
            xaxis=dict(
                title='Длина (см)',
                backgroundcolor="rgb(230, 230,230)",
                gridcolor="white",
                showbackground=True,
                range=[0, stack.base_length]
            ),
            yaxis=dict(
                title='Высота (см)',
                backgroundcolor="rgb(230, 230,230)",
                gridcolor="white",
                showbackground=True,
                range=[0, total_height + 10]
            ),
            zaxis=dict(
                title='Ширина (см)',
                backgroundcolor="rgb(230, 230,230)",
                gridcolor="white",
                showbackground=True,
                range=[0, stack.base_width]
            ),
            aspectmode='data',
            camera=dict(
                eye=dict(x=1.5, y=1.5, z=1.5)
            )
        ),
        title=dict(
            text=f'3D Визуализация: {stack.name}',
            font=dict(size=20)
        ),
        showlegend=True,
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01
        ),
        height=800,
        margin=dict(l=0, r=0, t=40, b=0)
    )
    
    return fig


def create_utilization_chart(stack: StorageStack):
    """Создать диаграмму использования полок"""
    data = []
    for shelf in reversed(stack.shelves):
        shelf_name = f"Полка {shelf.level}"
        if shelf.reserved_for_empty:
            shelf_name += " 🔼 БУФЕР"
        
        occupied_m2 = shelf.occupied_area / 10000
        free_m2 = shelf.free_area / 10000
        
        data.append({
            'Полка': shelf_name,
            'Занято (м²)': round(occupied_m2, 3),
            'Свободно (м²)': round(free_m2, 3),
            'Использование (%)': round(shelf.utilization_percent, 1),
            'Тар на полке': len(shelf.containers),
            'Вес (кг)': round(shelf.current_weight, 1)
        })
    
    df = pd.DataFrame(data)
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        name='Занято',
        x=df['Полка'],
        y=df['Занято (м²)'],
        marker_color='#4169E1',
        text=df['Занято (м²)'],
        textposition='inside',
        texttemplate='%{text:.3f}м²',
        hovertemplate='<b>%{x}</b><br>Занято: %{y:.3f} м²<br>Тар: %{customdata[0]}<br>Вес: %{customdata[1]} кг<extra></extra>',
        customdata=df[['Тар на полке', 'Вес (кг)']].values
    ))
    
    fig.add_trace(go.Bar(
        name='Свободно',
        x=df['Полка'],
        y=df['Свободно (м²)'],
        marker_color='#D3D3D3',
        text=df['Свободно (м²)'],
        textposition='inside',
        texttemplate='%{text:.3f}м²',
        hovertemplate='<b>%{x}</b><br>Свободно: %{y:.3f} м²<extra></extra>'
    ))
    
    # Добавляем линию процента использования
    fig.add_trace(go.Scatter(
        name='% использования',
        x=df['Полка'],
        y=df['Использование (%)'] / 100 * df['Занято (м²)'].max() * 1.2,
        mode='lines+markers+text',
        marker=dict(size=10, color='#FF8C00'),
        line=dict(color='#FF8C00', width=3),
        text=df['Использование (%)'].astype(str) + '%',
        textposition='top center',
        yaxis='y2',
        hovertemplate='<b>%{x}</b><br>Использование: %{text}<extra></extra>'
    ))
    
    fig.update_layout(
        barmode='stack',
        title='Использование площади полок',
        xaxis_title='Полки (снизу вверх)',
        yaxis_title='Площадь (м²)',
        yaxis2=dict(
            title='Использование (%)',
            overlaying='y',
            side='right',
            range=[0, 120]
        ),
        height=450,
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    return fig


def save_warehouse_to_json():
    """Сохранить состояние склада в JSON"""
    if st.session_state.warehouse is None:
        return None
    
    warehouse = st.session_state.warehouse
    state = {
        'warehouse_name': warehouse.name,
        'num_stacks': len(warehouse.stacks),
        'stacks': [],
        'containers': [],
        'container_counter': st.session_state.container_counter
    }
    
    # Сохраняем все стеллажи
    for stack in warehouse.stacks:
        stack_data = {
            'name': stack.name,
            'base_length': stack.base_length,
            'base_width': stack.base_width,
            'shelves': []
        }
        
        for shelf in stack.shelves:
            stack_data['shelves'].append({
                'level': shelf.level,
                'max_weight': shelf.max_weight,
                'height': shelf.height,
                'reserved_for_empty': shelf.reserved_for_empty,
                'containers_ids': [c.id for c in shelf.containers]
            })
        
        state['stacks'].append(stack_data)
    
    # Сохраняем все тары
    for container in st.session_state.containers:
        state['containers'].append({
            'id': container.id,
            'name': container.name,
            'weight': container.weight,
            'length': container.length,
            'width': container.width,
            'height': container.height,
            'is_empty': container.is_empty,
            'priority_parts': container.priority_parts,
            'content': container.content,
            'shelf_level': container.shelf_level
        })
    
    return json.dumps(state, indent=2, ensure_ascii=False)


def load_warehouse_from_json(json_str: str):
    """Загрузить состояние склада из JSON"""
    try:
        state = json.loads(json_str)
        
        # Создаем склад
        warehouse = Warehouse(state['warehouse_name'])
        
        # Создаем тары (сначала, чтобы можно было их найти по ID)
        containers = []
        containers_dict = {}
        for c_data in state['containers']:
            container = Container(
                id=c_data['id'],
                name=c_data['name'],
                weight=c_data['weight'],
                length=c_data['length'],
                width=c_data['width'],
                height=c_data['height'],
                is_empty=c_data['is_empty'],
                priority_parts=c_data['priority_parts'],
                content=c_data['content'],
                shelf_level=c_data.get('shelf_level')
            )
            containers.append(container)
            containers_dict[container.id] = container
        
        # Создаем стеллажи и восстанавливаем размещение
        for stack_data in state['stacks']:
            stack = StorageStack(
                name=stack_data['name'],
                base_length=stack_data['base_length'],
                base_width=stack_data['base_width']
            )
            
            # Добавляем полки
            for shelf_data in stack_data['shelves']:
                stack.add_shelf(
                    max_weight=shelf_data['max_weight'],
                    height=shelf_data['height'],
                    reserved_for_empty=shelf_data['reserved_for_empty']
                )
            
            # Восстанавливаем размещение тар на полках
            for shelf_idx, shelf_data in enumerate(stack_data['shelves']):
                shelf = stack.shelves[shelf_idx]
                for container_id in shelf_data.get('containers_ids', []):
                    if container_id in containers_dict:
                        container = containers_dict[container_id]
                        shelf.containers.append(container)
                        container.shelf_level = shelf.level
            
            warehouse.add_stack(stack)
        
        # Обновляем session state
        st.session_state.warehouse = warehouse
        st.session_state.containers = containers
        st.session_state.container_counter = state['container_counter']
        st.session_state.num_stacks = len(warehouse.stacks)
        
        return True
    except Exception as e:
        st.error(f"Ошибка загрузки данных: {e}")
        return False


def export_warehouse_to_excel(warehouse: Warehouse, containers: List[Container]):
    """Экспорт данных склада в Excel"""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Лист 1: Общая информация по складу
        total_stats = warehouse.get_total_statistics()
        info_data = {
            'Параметр': [
                'Название склада',
                'Количество стеллажей',
                'Общее количество полок',
                'Общая площадь (м²)',
                'Занятая площадь (м²)',
                'Использование (%)',
                'Всего тар размещено',
                'Тар не размещено',
                'Общий вес (кг)'
            ],
            'Значение': [
                total_stats['warehouse_name'],
                total_stats['total_stacks'],
                total_stats['total_shelves'],
                f"{total_stats['total_area_m2']:.2f}",
                f"{total_stats['occupied_area_m2']:.2f}",
                f"{total_stats['utilization_percent']:.1f}",
                total_stats['total_containers'],
                total_stats['unplaced_containers'],
                f"{total_stats['total_weight_kg']:.1f}"
            ]
        }
        df_info = pd.DataFrame(info_data)
        df_info.to_excel(writer, sheet_name='Общая информация', index=False)
        
        # Лист 2: Информация по стеллажам
        stacks_data = []
        for stack in warehouse.stacks:
            stats = stack.get_statistics()
            stacks_data.append({
                'Стеллаж': stack.name,
                'Полок': stats['total_shelves'],
                'Длина (см)': stack.base_length,
                'Ширина (см)': stack.base_width,
                'Площадь (м²)': f"{stats['total_area_m2']:.2f}",
                'Занято (м²)': f"{stats['occupied_area_m2']:.2f}",
                'Использование (%)': f"{stats['utilization_percent']:.1f}",
                'Тар': stats['total_containers'],
                'Вес (кг)': f"{stats['total_weight_kg']:.1f}"
            })
        df_stacks = pd.DataFrame(stacks_data)
        df_stacks.to_excel(writer, sheet_name='Стеллажи', index=False)
        
        # Лист 3: Все тары
        containers_data = []
        for c in containers:
            # Находим стеллаж, на котором размещена тара
            stack_name = 'Не размещена'
            for stack in warehouse.stacks:
                for shelf in stack.shelves:
                    if c in shelf.containers:
                        stack_name = stack.name
                        break
            
            containers_data.append({
                'ID': c.id,
                'Название': c.name,
                'Стеллаж': stack_name,
                'Полка': c.shelf_level if c.shelf_level is not None else '-',
                'Тип': 'Пустая' if c.is_empty else ('Приоритет' if c.priority_parts else 'Обычная'),
                'Вес (кг)': c.weight,
                'Длина (см)': c.length,
                'Ширина (см)': c.width,
                'Высота (см)': c.height,
                'Содержимое': c.content if c.content else '-'
            })
        df_containers = pd.DataFrame(containers_data)
        df_containers.to_excel(writer, sheet_name='Тары', index=False)
        
        # Лист 4: Детальное размещение по полкам
        placement_data = []
        for stack in warehouse.stacks:
            for shelf in stack.shelves:
                for container in shelf.containers:
                    placement_data.append({
                        'Стеллаж': stack.name,
                        'Полка': shelf.level,
                        'Зарезервирована': 'Да' if shelf.reserved_for_empty else 'Нет',
                        'Тара': container.name,
                        'ID': container.id,
                        'Вес (кг)': container.weight,
                        'Размер (ДxШxВ)': f"{container.length}x{container.width}x{container.height}",
                        'Тип': 'Пустая' if container.is_empty else ('Приоритет' if container.priority_parts else 'Обычная')
                    })
        df_placement = pd.DataFrame(placement_data)
        df_placement.to_excel(writer, sheet_name='Размещение', index=False)
    
    output.seek(0)
    return output.getvalue()


def load_posts_from_excel(uploaded_file) -> List[Post]:
    """
    Загрузить посты из Excel файла
    Ожидаемый формат:
    - Колонки: Model, Артикул, Наименование на русском языке, Пост, L(mm), W(mm), H(mm) и др.
    """
    try:
        df = pd.read_excel(uploaded_file)
        
        # Проверка обязательных колонок (гибкая проверка)
        required_mapping = {
            'Пост': ['Пост', 'Post'],
            'Название': ['Наименование на русском языке', 'Название', 'Name', 'Наименование'],
            'Артикул': ['Артикул', 'Article', 'Model'],
            'Длина': ['L(mm)', 'Длина(см)', 'Длина', 'Length'],
            'Ширина': ['W(mm)', 'Ширина(см)', 'Ширина', 'Width'],
            'Высота': ['H(mm)', 'Высота(см)', 'Высота', 'Height']
        }
        
        # Найдем соответствия колонок
        col_mapping = {}
        for key, possible_names in required_mapping.items():
            found = False
            for col in df.columns:
                if col in possible_names:
                    col_mapping[key] = col
                    found = True
                    break
            if not found:
                st.error(f"Не найдена колонка для '{key}'. Ожидаются: {', '.join(possible_names)}")
                return []
        
        # Группируем по постам
        posts_dict = {}
        container_counter = 1
        
        for _, row in df.iterrows():
            post_num = str(row[col_mapping['Пост']]).strip()
            
            if pd.isna(post_num) or post_num == 'nan' or not post_num:
                continue
            
            if post_num not in posts_dict:
                posts_dict[post_num] = Post(post_number=post_num)
            
            # Определяем единицы измерения и конвертируем
            length_col = col_mapping['Длина']
            width_col = col_mapping['Ширина']
            height_col = col_mapping['Высота']
            
            # Если в мм - конвертируем в см
            is_mm = 'mm' in length_col.lower() or 'мм' in length_col.lower()
            conversion_factor = 0.1 if is_mm else 1.0
            
            length = float(row[length_col]) * conversion_factor
            width = float(row[width_col]) * conversion_factor
            height = float(row[height_col]) * conversion_factor
            
            # Получаем название и артикул
            name = str(row[col_mapping['Название']]).strip()
            article = str(row[col_mapping['Артикул']]).strip() if col_mapping['Артикул'] in row.index else ""
            
            # Пытаемся получить материал если есть
            material = ""
            if 'Материал' in df.columns:
                material = str(row['Материал']).strip()
            elif 'Линия' in df.columns:
                material = str(row['Линия']).strip()
            else:
                material = article  # Используем артикул как материал для группировки
            
            # Вес по умолчанию или из колонки
            weight = 10.0  # Вес по умолчанию
            if 'Вес(кг)' in df.columns:
                weight = float(row['Вес(кг)'])
            elif 'STD Pack (MOQ)' in df.columns:
                # Предполагаем вес пропорционален упаковке
                weight = float(row['STD Pack (MOQ)']) * 0.5
            
            # Создаем контейнер
            container = Container(
                id=f"{article}_{container_counter:03d}" if article else f"P{post_num}_C{container_counter:03d}",
                name=name,
                weight=weight,
                length=length,
                width=width,
                height=height,
                material=material,
                post_number=post_num,
                content=f"{article}: {name}" if article else name
            )
            
            posts_dict[post_num].containers.append(container)
            container_counter += 1
        
        return list(posts_dict.values())
    
    except Exception as e:
        st.error(f"Ошибка при загрузке Excel: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return []


def create_stacks_for_post(post: Post, base_length: float, base_width: float, 
                           num_shelves: int, shelf_max_weight: float) -> List[StorageStack]:
    """
    Создать стеллажи для конкретного поста с учетом группировки по материалам
    """
    post.calculate_requirements(base_length, base_width)
    
    stacks = []
    
    # Создаем необходимое количество стеллажей
    for i in range(post.required_stacks):
        stack = StorageStack(
            name=f"Пост_{post.post_number}_Стеллаж_{i+1}",
            base_length=base_length,
            base_width=base_width
        )
        
        # Добавляем полки с оптимальной высотой
        for shelf_idx in range(num_shelves):
            is_top = shelf_idx == num_shelves - 1
            stack.add_shelf(
                max_weight=shelf_max_weight,
                height=post.optimal_shelf_height,
                reserved_for_empty=is_top
            )
        
        stacks.append(stack)
    
    return stacks


def distribute_post_containers_by_material(post: Post, stacks: List[StorageStack]) -> Dict:
    """
    Распределить коробки поста по стеллажам с строгой группировкой:
    1. Сначала группируем по модели/артикулу
    2. Внутри модели группируем по материалу
    3. Ящики одной модели с одним материалом стоят строго друг за другом
    """
    # Создаем составной ключ: артикул (из id) + материал
    # Извлекаем артикул из ID контейнера (формат: "АРТИКУЛ_NNN")
    groups = {}
    for container in post.containers:
        # Получаем артикул из ID (до первого underscore)
        article = container.id.split('_')[0] if '_' in container.id else container.id
        material = container.material or "unknown"
        
        # Составной ключ: артикул + материал
        group_key = f"{article}|{material}"
        
        if group_key not in groups:
            groups[group_key] = {
                'article': article,
                'material': material,
                'containers': []
            }
        groups[group_key].append(container)
    
    # Сортируем группы:
    # 1. По артикулу (алфавитный порядок)
    # 2. По общему весу группы (тяжелые первыми)
    sorted_groups = sorted(
        groups.items(),
        key=lambda x: (x[1]['article'], -sum(c.weight for c in x[1]['containers']))
    )
    
    placement_stats = {
        'total_containers': len(post.containers),
        'placed_containers': 0,
        'unplaced_containers': 0,
        'by_material': {},
        'by_stack': {},
        'by_article': {},
        'placement_log': []
    }
    
    current_stack_idx = 0
    current_shelf_in_stack = {}  # Отслеживаем текущую полку на каждом стеллаже
    
    for stack in stacks:
        current_shelf_in_stack[stack.name] = 0
    
    for group_key, group_data in sorted_groups:
        article = group_data['article']
        material = group_data['material']
        containers_list = group_data['containers']
        
        # Сортируем контейнеры в группе по весу (тяжелые вниз)
        containers_list.sort(key=lambda x: x.weight, reverse=True)
        
        group_stats = {'placed': 0, 'not_placed': 0}
        
        # Размещаем ВСЕ контейнеры группы последовательно
        for container in containers_list:
            placed = False
            
            # Пытаемся разместить на текущем стеллаже
            if current_stack_idx < len(stacks):
                stack = stacks[current_stack_idx]
                available_shelves = [s for s in stack.shelves if not s.reserved_for_empty]
                
                # Пытаемся разместить начиная с текущей полки
                for shelf_idx in range(current_shelf_in_stack[stack.name], len(available_shelves)):
                    shelf = available_shelves[shelf_idx]
                    
                    if shelf.can_add_container(container):
                        shelf.add_container(container)
                        container.placement_info = {
                            'stack': stack.name,
                            'shelf': shelf.level,
                            'x': 0,  # Упрощенно
                            'y': shelf.level * post.optimal_shelf_height
                        }
                        placed = True
                        placement_stats['placed_containers'] += 1
                        group_stats['placed'] += 1
                        
                        # Обновляем статистику
                        if stack.name not in placement_stats['by_stack']:
                            placement_stats['by_stack'][stack.name] = 0
                        placement_stats['by_stack'][stack.name] += 1
                        
                        if article not in placement_stats['by_article']:
                            placement_stats['by_article'][article] = 0
                        placement_stats['by_article'][article] += 1
                        
                        placement_stats['placement_log'].append({
                            'container': container.name,
                            'article': article,
                            'material': material,
                            'stack': stack.name,
                            'shelf': shelf.level,
                            'weight': container.weight
                        })
                        
                        # Обновляем текущую полку для этого стеллажа
                        current_shelf_in_stack[stack.name] = shelf_idx
                        break
                
                # Если не поместилось на текущей полке, переходим к следующей
                if not placed and current_shelf_in_stack[stack.name] < len(available_shelves) - 1:
                    current_shelf_in_stack[stack.name] += 1
                    # Повторяем попытку на следующей полке
                    shelf = available_shelves[current_shelf_in_stack[stack.name]]
                    if shelf.can_add_container(container):
                        shelf.add_container(container)
                        container.placement_info = {
                            'stack': stack.name,
                            'shelf': shelf.level,
                            'x': 0,
                            'y': shelf.level * post.optimal_shelf_height
                        }
                        placed = True
                        placement_stats['placed_containers'] += 1
                        group_stats['placed'] += 1
                        
                        if stack.name not in placement_stats['by_stack']:
                            placement_stats['by_stack'][stack.name] = 0
                        placement_stats['by_stack'][stack.name] += 1
                        
                        if article not in placement_stats['by_article']:
                            placement_stats['by_article'][article] = 0
                        placement_stats['by_article'][article] += 1
                        
                        placement_stats['placement_log'].append({
                            'container': container.name,
                            'article': article,
                            'material': material,
                            'stack': stack.name,
                            'shelf': shelf.level,
                            'weight': container.weight
                        })
            
            if not placed:
                # Переходим к следующему стеллажу
                current_stack_idx += 1
                if current_stack_idx < len(stacks):
                    current_shelf_in_stack[stacks[current_stack_idx].name] = 0
                    # Повторяем попытку на новом стеллаже
                    stack = stacks[current_stack_idx]
                    available_shelves = [s for s in stack.shelves if not s.reserved_for_empty]
                    if available_shelves:
                        shelf = available_shelves[0]
                        if shelf.can_add_container(container):
                            shelf.add_container(container)
                            container.placement_info = {
                                'stack': stack.name,
                                'shelf': shelf.level,
                                'x': 0,
                                'y': shelf.level * post.optimal_shelf_height
                            }
                            placed = True
                            placement_stats['placed_containers'] += 1
                            group_stats['placed'] += 1
                            
                            if stack.name not in placement_stats['by_stack']:
                                placement_stats['by_stack'][stack.name] = 0
                            placement_stats['by_stack'][stack.name] += 1
                            
                            if article not in placement_stats['by_article']:
                                placement_stats['by_article'][article] = 0
                            placement_stats['by_article'][article] += 1
                            
                            placement_stats['placement_log'].append({
                                'container': container.name,
                                'article': article,
                                'material': material,
                                'stack': stack.name,
                                'shelf': shelf.level,
                                'weight': container.weight
                            })
            
            if not placed:
                placement_stats['unplaced_containers'] += 1
                group_stats['not_placed'] += 1
        
        # Статистика по материалам
        material_key = f"{article}_{material}"
        placement_stats['by_material'][material_key] = group_stats
        
        # После размещения группы НЕ переходим к следующему стеллажу
        # Продолжаем заполнять текущий стеллаж следующей группой
    
    return placement_stats


def save_state_to_file():
    """Сохранить состояние в JSON файл"""
    if st.session_state.stack is None:
        return None
    
    state = {
        'stack_name': st.session_state.stack.name,
        'base_length': st.session_state.stack.base_length,
        'base_width': st.session_state.stack.base_width,
        'shelves': [],
        'containers': [],
        'container_counter': st.session_state.container_counter
    }
    
    for shelf in st.session_state.stack.shelves:
        state['shelves'].append({
            'level': shelf.level,
            'max_weight': shelf.max_weight,
            'height': shelf.height,
            'reserved_for_empty': shelf.reserved_for_empty
        })
    
    for container in st.session_state.containers:
        state['containers'].append({
            'id': container.id,
            'name': container.name,
            'weight': container.weight,
            'length': container.length,
            'width': container.width,
            'height': container.height,
            'is_empty': container.is_empty,
            'priority_parts': container.priority_parts,
            'content': container.content,
            'shelf_level': container.shelf_level
        })
    
    return json.dumps(state, indent=2, ensure_ascii=False)


def load_state_from_json(json_str: str):
    """Загрузить состояние из JSON"""
    try:
        state = json.loads(json_str)
        
        # Создаем стеллаж
        stack = StorageStack(
            name=state['stack_name'],
            base_length=state['base_length'],
            base_width=state['base_width']
        )
        
        # Добавляем полки
        for shelf_data in state['shelves']:
            stack.add_shelf(
                max_weight=shelf_data['max_weight'],
                height=shelf_data['height'],
                reserved_for_empty=shelf_data['reserved_for_empty']
            )
        
        # Создаем тары
        containers = []
        for c_data in state['containers']:
            container = Container(
                id=c_data['id'],
                name=c_data['name'],
                weight=c_data['weight'],
                length=c_data['length'],
                width=c_data['width'],
                height=c_data['height'],
                is_empty=c_data['is_empty'],
                priority_parts=c_data['priority_parts'],
                content=c_data['content'],
                shelf_level=c_data.get('shelf_level')
            )
            containers.append(container)
        
        st.session_state.stack = stack
        st.session_state.containers = containers
        st.session_state.container_counter = state['container_counter']
        
        # Размещаем тары обратно на полки
        if any(c.shelf_level is not None for c in containers):
            stack.organize_containers(containers)
        
        return True
    except Exception as e:
        st.error(f"Ошибка загрузки данных: {e}")
        return False


def export_to_excel(stack: StorageStack, containers: List[Container]):
    """Экспорт данных в Excel"""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Лист 1: Общая информация
        stats = stack.get_statistics()
        info_data = {
            'Параметр': [
                'Название стеллажа',
                'Количество полок',
                'Длина (см)',
                'Ширина (см)',
                'Общая площадь (м²)',
                'Занятая площадь (м²)',
                'Свободная площадь (м²)',
                'Использование (%)',
                'Всего тар',
                'Общий вес (кг)',
                'Тар в буфере'
            ],
            'Значение': [
                stats['name'],
                stats['total_shelves'],
                stack.base_length,
                stack.base_width,
                f"{stats['total_area_m2']:.2f}",
                f"{stats['occupied_area_m2']:.2f}",
                f"{stats['free_area_m2']:.2f}",
                f"{stats['utilization_percent']:.1f}",
                stats['total_containers'],
                f"{stats['total_weight_kg']:.1f}",
                stats['empty_buffer_count']
            ]
        }
        df_info = pd.DataFrame(info_data)
        df_info.to_excel(writer, sheet_name='Общая информация', index=False)
        
        # Лист 2: Полки
        shelves_data = []
        for shelf in stack.shelves:
            shelves_data.append({
                'Полка №': shelf.level,
                'Тип': 'БУФЕР (пустая тара)' if shelf.reserved_for_empty else 'Обычная',
                'Высота (см)': shelf.height,
                'Макс. нагрузка (кг)': shelf.max_weight,
                'Текущий вес (кг)': f"{shelf.current_weight:.1f}",
                'Площадь (м²)': f"{shelf.total_area/10000:.2f}",
                'Занято (м²)': f"{shelf.occupied_area/10000:.2f}",
                'Свободно (м²)': f"{shelf.free_area/10000:.2f}",
                'Использование (%)': f"{shelf.utilization_percent:.1f}",
                'Количество тар': len(shelf.containers)
            })
        df_shelves = pd.DataFrame(shelves_data)
        df_shelves.to_excel(writer, sheet_name='Полки', index=False)
        
        # Лист 3: Тары
        containers_data = []
        for c in containers:
            containers_data.append({
                'ID': c.id,
                'Название': c.name,
                'Длина (см)': c.length,
                'Ширина (см)': c.width,
                'Высота (см)': c.height,
                'Площадь (см²)': f"{c.base_area:.0f}",
                'Объем (см³)': f"{c.volume:.0f}",
                'Вес (кг)': c.weight,
                'Тип': 'Пустая' if c.is_empty else ('Приоритет' if c.priority_parts else 'Обычная'),
                'Содержимое': c.content if c.content else '-',
                'Полка': f"Полка {c.shelf_level}" if c.shelf_level is not None else 'Не размещена'
            })
        df_containers = pd.DataFrame(containers_data)
        df_containers.to_excel(writer, sheet_name='Тары', index=False)
        
        # Лист 4: Размещение по полкам
        placement_data = []
        for shelf in stack.shelves:
            for container in shelf.containers:
                placement_data.append({
                    'Полка': shelf.level,
                    'Тара': container.name,
                    'Тип тары': 'Пустая' if container.is_empty else ('Приоритет' if container.priority_parts else 'Обычная'),
                    'Вес (кг)': container.weight,
                    'Размеры (ДxШxВ)': f"{container.length}x{container.width}x{container.height}",
                    'Содержимое': container.content if container.content else '-'
                })
        if placement_data:
            df_placement = pd.DataFrame(placement_data)
            df_placement.to_excel(writer, sheet_name='Размещение', index=False)
    
    output.seek(0)
    return output


def main():
    st.set_page_config(
        page_title="Калькулятор Штабелей",
        page_icon="📦",
        layout="wide"
    )
    
    st.title("📦 Система Расчета Штабелей для Тар")
    st.markdown("---")
    
    # Инициализация session state
    if 'warehouse' not in st.session_state:
        st.session_state.warehouse = None
    if 'containers' not in st.session_state:
        st.session_state.containers = []
    if 'container_counter' not in st.session_state:
        st.session_state.container_counter = 1
    if 'num_stacks' not in st.session_state:
        st.session_state.num_stacks = 1
    
    # Боковая панель для настроек
    with st.sidebar:
        st.header("⚙️ Настройки Стеллажа")
        
        # Параметры стеллажа
        st.subheader("📐 Размеры Стеллажа")
        
        col1, col2 = st.columns(2)
        with col1:
            base_length = st.number_input("Длина (см)", min_value=50, value=200, step=10)
        with col2:
            base_width = st.number_input("Ширина (см)", min_value=50, value=120, step=10)
        
        # Раздел сохранения/загрузки
        st.markdown("---")
        with st.expander("💾 Сохранение/Загрузка", expanded=False):
            st.markdown("**Защита от потери данных**")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("💾 Сохранить", use_container_width=True, key="save_btn"):
                    if st.session_state.warehouse:
                        json_data = save_warehouse_to_json()
                        if json_data:
                            st.download_button(
                                label="📥 Скачать JSON",
                                data=json_data,
                                file_name=f"склад_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                                mime="application/json",
                                use_container_width=True,
                                key="download_json"
                            )
            
            with col2:
                uploaded_file = st.file_uploader("📂 Загрузить", type=['json'], label_visibility="collapsed", key="upload_json")
                if uploaded_file is not None:
                    json_str = uploaded_file.read().decode('utf-8')
                    if load_warehouse_from_json(json_str):
                        st.success("✅ Данные загружены!")
                        st.rerun()
            
            if st.session_state.warehouse and st.session_state.containers:
                st.markdown("**Экспорт в Excel**")
                excel_data = export_warehouse_to_excel(st.session_state.warehouse, st.session_state.containers)
                st.download_button(
                    label="📊 Скачать Excel отчет",
                    data=excel_data,
                    file_name=f"отчет_склад_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="download_excel"
                )
    
    # Основная область - больше не требуется создание склада
    warehouse = st.session_state.warehouse
    
    # Вкладки
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📦 Управление Тарами", "📊 Визуализация", "📈 Статистика", "🔄 Распределение", "🏭 Работа с Постами"])
    
    with tab1:
        if warehouse is None:
            st.info("👈 Сначала загрузите Excel файл с постами на вкладке 'Работа с Постами' или загрузите сохраненную конфигурацию")
        else:
            st.header("Добавление Тар")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                container_name = st.text_input("Название тары", f"Тара {st.session_state.container_counter}")
                weight = st.number_input("Вес (кг)", min_value=0.1, value=50.0, step=5.0)
            
            with col2:
                length = st.number_input("Длина (см)", min_value=10, value=50, step=5)
                width = st.number_input("Ширина (см)", min_value=10, value=40, step=5)
            
            with col3:
                height = st.number_input("Высота (см)", min_value=10, value=40, step=5)
                is_empty = st.checkbox("Пустая тара")
            
            if not is_empty:
                col1, col2 = st.columns(2)
                with col1:
                    priority = st.checkbox("Приоритетные детали (требует доступа)")
                with col2:
                    content = st.text_input("Содержимое", "Детали")
            else:
                priority = False
                content = ""
            
            if st.button("➕ Добавить тару", type="primary"):
                container = Container(
                    id=f"T{st.session_state.container_counter:03d}",
                    name=container_name,
                    weight=weight,
                    length=length,
                    width=width,
                    height=height,
                    is_empty=is_empty,
                    priority_parts=priority,
                    content=content
                )
                st.session_state.containers.append(container)
                st.session_state.container_counter += 1
                st.success(f"✅ Тара '{container_name}' добавлена!")
                st.rerun()
            
            st.markdown("---")
            st.subheader("Список Тар")
            
            if st.session_state.containers:
                # Создаем DataFrame для отображения
                containers_data = []
                for c in st.session_state.containers:
                    # Находим стеллаж, на котором размещена тара
                    stack_name = 'Не размещена'
                    for stack in warehouse.stacks:
                        for shelf in stack.shelves:
                            if c in shelf.containers:
                                stack_name = stack.name
                                break
                        if stack_name != 'Не размещена':
                            break
                    
                    containers_data.append({
                        'ID': c.id,
                        'Название': c.name,
                        'Стеллаж': stack_name,
                        'Полка': f"Полка {c.shelf_level}" if c.shelf_level is not None else "-",
                        'Размеры (ДxШxВ)': f"{c.length}x{c.width}x{c.height}",
                        'Вес (кг)': c.weight,
                        'Тип': 'Пустая' if c.is_empty else ('Приоритет' if c.priority_parts else 'Обычная'),
                        'Содержимое': c.content if c.content else '-'
                    })
                
                df = pd.DataFrame(containers_data)
                st.dataframe(df, use_container_width=True)
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("🎯 Распределить по складу", type="primary"):
                        # Очищаем старые размещения
                        for stack in warehouse.stacks:
                            for shelf in stack.shelves:
                                shelf.containers.clear()
                        
                        # Распределяем контейнеры по всем стеллажам
                        placement_stats = warehouse.distribute_containers(st.session_state.containers)
                        
                        st.success(f"✅ Размещено: {placement_stats['placed']} тар")
                        if placement_stats['not_placed'] > 0:
                            st.warning(f"⚠️ Не размещено: {placement_stats['not_placed']} тар")
                            st.info("💡 Попробуйте добавить еще стеллажей или уменьшить количество тар")
                        
                        # Показываем распределение по стеллажам
                        st.markdown("**Распределение по стеллажам:**")
                        for stack_name, count in placement_stats['by_stack'].items():
                            st.write(f"- {stack_name}: {count} тар")
                        
                        st.rerun()
                
                with col2:
                    if st.button("🗑️ Очистить все", type="secondary"):
                        st.session_state.containers.clear()
                        for stack in warehouse.stacks:
                            for shelf in stack.shelves:
                                shelf.containers.clear()
                        st.rerun()
                
                with col3:
                    if st.button("📋 Загрузить пример", type="secondary"):
                        example_containers = [
                            Container("T001", "Тяжелая тара №1", 80, 60, 40, 45, content="Металл"),
                            Container("T002", "Тяжелая тара №2", 75, 60, 40, 45, content="Детали"),
                            Container("T003", "Средняя тара", 50, 50, 40, 40, content="Запчасти"),
                            Container("T004", "Срочная", 30, 40, 30, 35, priority_parts=True, content="Заказ А"),
                            Container("T005", "Срочная №2", 25, 40, 30, 35, priority_parts=True, content="Заказ Б"),
                            Container("T006", "Пустая №1", 5, 40, 30, 30, is_empty=True),
                            Container("T007", "Пустая №2", 6, 40, 30, 30, is_empty=True),
                        ]
                        st.session_state.containers = example_containers
                        st.session_state.container_counter = 8
                        st.rerun()
            else:
                st.info("Список тар пуст. Добавьте тары выше.")
    
    with tab2:
        if warehouse is None:
            st.info("👈 Сначала загрузите Excel файл с постами на вкладке 'Работа с Постами' или загрузите сохраненную конфигурацию")
        else:
            st.header("3D Визуализация Стеллажей")
            
            # Выбор стеллажа для визуализации
            stack_names = [s.name for s in warehouse.stacks]
            selected_stack_name = st.selectbox("Выберите стеллаж для визуализации", stack_names)
            selected_stack = next(s for s in warehouse.stacks if s.name == selected_stack_name)
            
            if any(shelf.containers for shelf in selected_stack.shelves):
                # Информационная панель
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.markdown("### 🔵 Обычные тары")
                    st.caption("Синий цвет")
                with col2:
                    st.markdown("### 🟠 Приоритетные")
                    st.caption("Оранжевый цвет")
                with col3:
                    st.markdown("### ⚪ Пустые (буфер)")
                    st.caption("Серый цвет")
                with col4:
                    total_tars = sum(len(s.containers) for s in selected_stack.shelves)
                    st.metric("Тар на стеллаже", total_tars)
                
                st.markdown("---")
                
                # 3D визуализация
                with st.spinner("Создание 3D модели..."):
                    fig = create_3d_visualization(selected_stack)
                    st.plotly_chart(fig, use_container_width=True)
                
                st.info("💡 **Управление:** Вращайте мышью | Zoom: колесико | Наведите на тару для деталей")
                
                st.markdown("---")
                
                # Диаграмма использования
                st.subheader("📊 Диаграмма использования полок")
                fig_util = create_utilization_chart(selected_stack)
                st.plotly_chart(fig_util, use_container_width=True)
                
                st.markdown("---")
                st.subheader("📐 Параметры стеллажа")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"**Длина:** {selected_stack.base_length} см")
                    st.write(f"**Ширина:** {selected_stack.base_width} см")
                with col2:
                    total_height = sum(s.height for s in selected_stack.shelves)
                    st.write(f"**Общая высота:** {total_height} см")
                    st.write(f"**Полок:** {len(selected_stack.shelves)}")
                with col3:
                    stats = selected_stack.get_statistics()
                    st.write(f"**Площадь основания:** {selected_stack.base_length * selected_stack.base_width / 10000:.2f} м²")
                    st.write(f"**Общий объем:** {selected_stack.base_length * selected_stack.base_width * total_height / 1000000:.2f} м³")
            else:
                st.info("📦 Сначала разместите тары на вкладке 'Управление Тарами'")
                st.markdown("""
                ### Как начать:
                1. Перейдите на вкладку **"Управление Тарами"**
                2. Нажмите **"Загрузить пример"** для быстрого теста
                3. Нажмите **"Распределить по складу"**
                4. Вернитесь сюда для просмотра 3D модели
                """)
    
    with tab3:
        if warehouse is None:
            st.info("👈 Сначала загрузите Excel файл с постами на вкладке 'Работа с Постами' или загрузите сохраненную конфигурацию")
        else:
            st.header("Статистика Склада")
            
            # Общая статистика по складу
            total_stats = warehouse.get_total_statistics()
            
            st.subheader("📊 Общая информация")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Стеллажей", total_stats['total_stacks'])
                st.metric("Полок", total_stats['total_shelves'])
            
            with col2:
                st.metric("Тар размещено", total_stats['total_containers'])
                st.metric("Не размещено", total_stats['unplaced_containers'])
            
            with col3:
                st.metric("Общая площадь", f"{total_stats['total_area_m2']:.2f} м²")
                st.metric("Занято", f"{total_stats['occupied_area_m2']:.2f} м²")
            
            with col4:
                st.metric("Использование", f"{total_stats['utilization_percent']:.1f}%")
                st.metric("Общий вес", f"{total_stats['total_weight_kg']:.1f} кг")
            
            st.markdown("---")
            
            # Статистика по каждому стеллажу
            st.subheader("📦 Детали по стеллажам")
            
            for stack in warehouse.stacks:
                stack_stats = stack.get_statistics()
                
                with st.expander(f"**{stack.name}** - Использование: {stack_stats['utilization_percent']:.1f}%", expanded=False):
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.write(f"**Полок:** {stack_stats['total_shelves']}")
                        st.write(f"**Тар:** {stack_stats['total_containers']}")
                    
                    with col2:
                        st.write(f"**Площадь:** {stack_stats['total_area_m2']:.2f} м²")
                        st.write(f"**Занято:** {stack_stats['occupied_area_m2']:.2f} м²")
                    
                    with col3:
                        st.write(f"**Свободно:** {stack_stats['free_area_m2']:.2f} м²")
                        st.write(f"**Использование:** {stack_stats['utilization_percent']:.1f}%")
                    
                    with col4:
                        st.write(f"**Вес:** {stack_stats['total_weight_kg']:.1f} кг")
                        st.write(f"**Буфер:** {stack_stats['empty_buffer_count']}")
                    
                    # Детали по полкам
                    st.markdown("**Полки:**")
                    for shelf in reversed(stack.shelves):
                        shelf_name = f"Полка {shelf.level}"
                        if shelf.reserved_for_empty:
                            shelf_name += " [БУФЕР]"
                        
                        st.write(f"- {shelf_name}: {len(shelf.containers)} тар, {shelf.utilization_percent:.1f}% использования")
    
    with tab4:
        if warehouse is None:
            st.info("👈 Сначала загрузите Excel файл с постами на вкладке 'Работа с Постами' или загрузите сохраненную конфигурацию")
        else:
            st.header("🔄 Анализ Распределения")
            
            st.info("""
            **Оптимальное распределение:** Система автоматически распределяет тары по всем стеллажам, 
            максимизируя использование площади и соблюдая все правила размещения.
            """)
            
            # Показываем общую статистику распределения
            total_stats = warehouse.get_total_statistics()
            
            st.subheader("📊 Эффективность распределения")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Всего тар", len(st.session_state.containers))
                st.metric("Размещено", total_stats['total_containers'])
            
            with col2:
                st.metric("Не размещено", total_stats['unplaced_containers'])
                placement_rate = (total_stats['total_containers'] / len(st.session_state.containers) * 100) if st.session_state.containers else 0
                st.metric("% размещения", f"{placement_rate:.1f}%")
            
            with col3:
                st.metric("Использование площади", f"{total_stats['utilization_percent']:.1f}%")
                st.metric("Доступных стеллажей", total_stats['total_stacks'])
            
            st.markdown("---")
            
            # Распределение по стеллажам
            st.subheader("📦 Загрузка стеллажей")
            
            stacks_data = []
            for stack in warehouse.stacks:
                stack_stats = stack.get_statistics()
                stacks_data.append({
                    'Стеллаж': stack.name,
                    'Тар': stack_stats['total_containers'],
                    'Использование %': round(stack_stats['utilization_percent'], 1),
                    'Занято м²': round(stack_stats['occupied_area_m2'], 2),
                    'Свободно м²': round(stack_stats['free_area_m2'], 2),
                    'Вес кг': round(stack_stats['total_weight_kg'], 1)
                })
            
            if stacks_data:
                df_stacks = pd.DataFrame(stacks_data)
                st.dataframe(df_stacks, use_container_width=True)
                
                # График распределения
                fig = go.Figure()
                
                fig.add_trace(go.Bar(
                    x=[d['Стеллаж'] for d in stacks_data],
                    y=[d['Тар'] for d in stacks_data],
                    name='Количество тар',
                    marker_color='#4169E1'
                ))
                
                fig.update_layout(
                    title="Распределение тар по стеллажам",
                    xaxis_title="Стеллаж",
                    yaxis_title="Количество тар",
                    height=400
                )
                
                st.plotly_chart(fig, use_container_width=True)
            
            # Неразмещенные тары
            if warehouse.unplaced_containers:
                st.markdown("---")
                st.subheader("⚠️ Неразмещенные тары")
                st.warning(f"Не удалось разместить {len(warehouse.unplaced_containers)} тар")
                
                unplaced_data = []
                for c in warehouse.unplaced_containers:
                    unplaced_data.append({
                        'Название': c.name,
                        'Тип': 'Пустая' if c.is_empty else ('Приоритет' if c.priority_parts else 'Обычная'),
                        'Размеры': f"{c.length}x{c.width}x{c.height}",
                        'Вес кг': c.weight
                    })
                
                df_unplaced = pd.DataFrame(unplaced_data)
                st.dataframe(df_unplaced, use_container_width=True)
                
                st.info("💡 Рекомендации: Добавьте больше стеллажей или уменьшите размер/вес тар")
    
    # Вкладка "Работа с Постами"
    with tab5:
        st.header("🏭 Работа с Постами")
        st.markdown("""
        Загрузите Excel файл с постами для автоматического расчета и расстановки тар по стеллажам.
        
        **Требования к Excel файлу:**
        - **Обязательные столбцы:** 
          - `Пост` - номер поста
          - `Наименование на русском языке` (или `Название`) - название детали
          - `Артикул` (или `Model`) - артикул детали
          - `L(mm)`, `W(mm)`, `H(mm)` - размеры в миллиметрах (будут автоматически конвертированы в см)
        - **Опциональные столбцы:** `Линия`, `Материал`, `Вес(кг)`, `STD Pack (MOQ)` и др.
        - Каждая строка - одна позиция/тара
        - Группировка по постам и линиям происходит автоматически
        
        **Правила размещения:**
        - ✅ Автоматический расчет оптимальной высоты стеллажа (макс. высота тары + 15-20 см)
        - ✅ Автоматический расчет необходимого количества стеллажей для каждого поста
        - ✅ Тары с одинаковым материалом/линией размещаются рядом друг с другом (в длину)
        - ✅ Соблюдение всех стандартных правил (тяжелые снизу, приоритетные доступны, пустые сверху)
        """)
        
        st.markdown("---")
        
        # Загрузка Excel файла
        uploaded_excel = st.file_uploader(
            "📂 Загрузите Excel файл с постами",
            type=['xlsx', 'xls'],
            help="Файл должен содержать столбцы: Пост, Наименование на русском языке, Артикул, L(mm), W(mm), H(mm)",
            key="upload_posts_excel"
        )
        
        if uploaded_excel is not None:
            try:
                # Загружаем посты из Excel
                posts = load_posts_from_excel(uploaded_excel)
                
                if posts:
                    st.success(f"✅ Загружено {len(posts)} постов")
                    
                    # Выбор поста для обработки
                    st.markdown("---")
                    st.subheader("📋 Выберите пост для создания стеллажей")
                    
                    # Создаем таблицу с информацией о постах
                    posts_info = []
                    for post in posts:
                        # Расчитываем требования для поста используя настройки из боковой панели
                        post.calculate_requirements(base_length, base_width)
                        
                        posts_info.append({
                            'Пост': post.post_number,
                            'Тар': len(post.containers),
                            'Материалов': len(set(c.material for c in post.containers if c.material)),
                            'Требуется стеллажей': post.required_stacks,
                            'Оптимальная высота полки (см)': f"{post.optimal_shelf_height:.1f}",
                            'Общий вес (кг)': f"{sum(c.weight for c in post.containers):.1f}"
                        })
                    
                    df_posts = pd.DataFrame(posts_info)
                    st.dataframe(df_posts, use_container_width=True, hide_index=True)
                    
                    # Выбор поста
                    selected_post_number = st.selectbox(
                        "Выберите пост",
                        options=[p.post_number for p in posts],
                        key="selected_post"
                    )
                    
                    selected_post = next(p for p in posts if p.post_number == selected_post_number)
                    
                    # Информация о выбранном посте
                    st.markdown("---")
                    st.subheader(f"📦 Пост: {selected_post.post_number}")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Тар", len(selected_post.containers))
                    with col2:
                        st.metric("Материалов", len(set(c.material for c in selected_post.containers if c.material)))
                    with col3:
                        st.metric("Требуется стеллажей", selected_post.required_stacks)
                    with col4:
                        st.metric("Высота полки (см)", f"{selected_post.optimal_shelf_height:.1f}")
                    
                    # Показываем распределение материалов
                    st.markdown("**📊 Распределение материалов:**")
                    material_stats = {}
                    for container in selected_post.containers:
                        mat = container.material if container.material else "Не указан"
                        if mat not in material_stats:
                            material_stats[mat] = {'count': 0, 'weight': 0}
                        material_stats[mat]['count'] += 1
                        material_stats[mat]['weight'] += container.weight
                    
                    material_data = []
                    for mat, stats in sorted(material_stats.items(), key=lambda x: x[1]['weight'], reverse=True):
                        material_data.append({
                            'Материал': mat,
                            'Количество тар': stats['count'],
                            'Общий вес (кг)': f"{stats['weight']:.1f}"
                        })
                    
                    df_materials = pd.DataFrame(material_data)
                    st.dataframe(df_materials, use_container_width=True, hide_index=True)
                    
                    # Параметры полок
                    st.markdown("---")
                    st.subheader("⚙️ Параметры полок")
                    
                    post_num_shelves = st.number_input(
                        "Количество полок",
                        min_value=3,
                        max_value=10,
                        value=5,
                        step=1,
                        key="post_num_shelves"
                    )
                    
                    # Кнопка создания стеллажей
                    if st.button("🔧 Создать стеллажи для поста", type="primary", use_container_width=True, key="create_post_stacks"):
                        # Пересчитываем требования с параметрами из боковой панели
                        selected_post.calculate_requirements(base_length, base_width)
                        
                        # Создаем стеллажи для поста
                        post_stacks = create_stacks_for_post(
                            selected_post,
                            base_length,
                            base_width,
                            post_num_shelves
                        )
                        
                        # Создаем временный склад для поста
                        post_warehouse = Warehouse(f"Склад для поста {selected_post.post_number}")
                        for stack in post_stacks:
                            post_warehouse.add_stack(stack)
                        
                        # Распределяем контейнеры по материалам
                        placement_stats = distribute_post_containers_by_material(
                            selected_post,
                            post_stacks
                        )
                        
                        # Сохраняем в session state
                        st.session_state.warehouse = post_warehouse
                        st.session_state.containers = selected_post.containers
                        
                        st.success(f"✅ Создано {len(post_stacks)} стеллажей для поста {selected_post.post_number}")
                        
                        # Показываем статистику размещения
                        st.markdown("---")
                        st.subheader("📊 Результаты размещения")
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Размещено тар", placement_stats['placed_containers'])
                        with col2:
                            st.metric("Не размещено", placement_stats['unplaced_containers'])
                        with col3:
                            placed_pct = (placement_stats['placed_containers'] / placement_stats['total_containers'] * 100) if placement_stats['total_containers'] > 0 else 0
                            st.metric("Успешность", f"{placed_pct:.1f}%")
                        
                        # Детальная таблица размещения
                        st.markdown("**🗂️ Детальное размещение:**")
                        
                        placement_data = []
                        for container in selected_post.containers:
                            if hasattr(container, 'placement_info') and container.placement_info:
                                # Извлекаем артикул из ID
                                article = container.id.split('_')[0] if '_' in container.id else container.id
                                
                                placement_data.append({
                                    'Артикул': article,
                                    'Название': container.name,
                                    'Материал': container.material or 'Не указан',
                                    'Вес (кг)': f"{container.weight:.1f}",
                                    'Размеры (см)': f"{container.length}×{container.width}×{container.height}",
                                    'Стеллаж': container.placement_info['stack'],
                                    'Полка': container.placement_info['shelf'],
                                    'Позиция (см)': f"({container.placement_info['x']:.1f}, {container.placement_info['y']:.1f})"
                                })
                        
                        if placement_data:
                            df_placement = pd.DataFrame(placement_data)
                            st.dataframe(df_placement, use_container_width=True, hide_index=True)
                            
                            # Группировка по артикулам и материалам
                            st.markdown("**📦 Группировка по артикулам и материалам:**")
                            
                            # Собираем данные по артикулам
                            article_groups = {}
                            for c in selected_post.containers:
                                if hasattr(c, 'placement_info') and c.placement_info:
                                    # Извлекаем артикул из ID
                                    article = c.id.split('_')[0] if '_' in c.id else c.id
                                    material = c.material or "unknown"
                                    key = f"{article}|{material}"
                                    
                                    if key not in article_groups:
                                        article_groups[key] = {
                                            'article': article,
                                            'material': material,
                                            'containers': [],
                                            'stacks': set()
                                        }
                                    article_groups[key]['containers'].append(c)
                                    article_groups[key]['stacks'].add(c.placement_info['stack'])
                            
                            # Показываем группировку
                            for key in sorted(article_groups.keys()):
                                group = article_groups[key]
                                stacks_list = ', '.join(sorted(group['stacks']))
                                st.write(f"**{group['article']}** ({group['material']}): {len(group['containers'])} шт. → Стеллажи: {stacks_list}")
                        else:
                            st.warning("Ни одна тара не была размещена")
                        
                        st.info("💡 Теперь вы можете перейти на вкладку 'Визуализация' или 'Статистика' для просмотра результатов")
                        
            except Exception as e:
                st.error(f"❌ Ошибка при обработке файла: {str(e)}")
                st.exception(e)
        else:
            st.info("👆 Загрузите Excel файл для начала работы с постами")
            
            # Пример формата Excel
            with st.expander("📄 Пример формата Excel файла"):
                st.markdown("""
                | Model | Артикул | Наименование на русском языке | Линия | Пост | L(mm) | W(mm) | H(mm) | STD Pack (MOQ) |
                |-------|---------|-------------------------------|--------|------|-------|-------|-------|----------------|
                | A123 | ART-001 | Деталь А1 | Линия 1 | П-001 | 800 | 600 | 400 | 10 |
                | A124 | ART-002 | Деталь А2 | Линия 1 | П-001 | 750 | 580 | 380 | 12 |
                | B201 | ART-101 | Компонент Б1 | Линия 2 | П-002 | 900 | 650 | 450 | 8 |
                | C301 | ART-201 | Узел С1 | Линия 3 | П-003 | 700 | 500 | 300 | 20 |
                
                **Примечание:** 
                - Размеры указываются в миллиметрах (мм) - автоматически конвертируются в сантиметры
                - Если нет колонки "Материал", используется "Линия" для группировки
                - Пример файла: `пример_посты_новый.xlsx`
                """)
                st.caption("Система автоматически определяет нужные колонки по их названиям")


if __name__ == "__main__":
    main()
