"""Incremental display model. New receipts must not recreate existing evidence cards."""
from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


class StepListModel(QAbstractListModel):
    ItemRole = int(Qt.UserRole) + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []

    def roleNames(self):
        # Preserve the existing QML delegate's modelData mapping.
        return {self.ItemRole: b'modelData'}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=Qt.DisplayRole):
        if role != self.ItemRole or not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        return dict(self._rows[index.row()])

    @staticmethod
    def _item(value):
        if not isinstance(value, dict) or any(not isinstance(value.get(key), str) for key in ('label', 'status', 'detail')):
            raise ValueError('A step requires string label, status and detail')
        return {**{key: value[key] for key in ('label', 'status', 'detail')}, 'full': value.get('full', True) is True}

    def append(self, value):
        row = self._item(value)
        index = len(self._rows)
        self.beginInsertRows(QModelIndex(), index, index)
        self._rows.append(row)
        self.endInsertRows()

    def replace(self, values):
        # A task switch intentionally resets the view; streaming updates do not.
        rows = [self._item(value) for value in values]
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def clear(self):
        self.replace([])
