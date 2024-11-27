import sys
import os
import pandas as pd
import paramiko
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QLabel, QComboBox, QListWidget, QListWidgetItem,
    QTextEdit, QMessageBox, QTableView, QAbstractItemView, QDialog,
    QLineEdit, QFormLayout, QGroupBox, QMenu
)
from PyQt5.QtCore import Qt, QAbstractTableModel, QVariant, QSize, QPoint
from PyQt5.QtGui import QTextDocument, QColor, QClipboard
from PyQt5.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle


class MultiLineDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super(MultiLineDelegate, self).__init__(parent)

    def paint(self, painter, option, index):
        text = index.data(Qt.DisplayRole)
        if text is None:
            text = ""
        painter.save()

        # Initialize the style option and prevent default text drawing
        self.initStyleOption(option, index)
        option.text = ""  # Prevent default text drawing
        style = option.widget.style()
        style.drawControl(QStyle.CE_ItemViewItem, option, painter)

        # Set up the QTextDocument
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        doc.setPlainText(text)

        # Calculate the rect for text
        text_rect = option.rect.adjusted(4, 2, -4, -2)
        doc.setTextWidth(text_rect.width() if text_rect.width() > 0 else 1)

        # Translate painter to the text rect top-left
        painter.translate(text_rect.topLeft())

        # Draw the text
        doc.drawContents(painter)

        painter.restore()

    def sizeHint(self, option, index):
        text = index.data(Qt.DisplayRole)
        if text is None:
            text = ""
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        # 최소 너비 설정 (0이면 오류 발생)
        text_width = option.rect.width() if option.rect.width() > 0 else 1
        doc.setTextWidth(text_width)
        doc.setPlainText(text)
        return QSize(int(doc.idealWidth()), int(doc.size().height()) + 4)  # 추가 여유 공간


class DataFrameModel(QAbstractTableModel):
    def __init__(self, df=pd.DataFrame()):
        super(DataFrameModel, self).__init__()
        self._df = df

    def setDataFrame(self, df):
        self.beginResetModel()
        self._df = df.copy()
        self.endResetModel()

    def rowCount(self, parent=None):
        return len(self._df.index)

    def columnCount(self, parent=None):
        if not self._df.empty:
            return len(self._df.columns)
        return 0

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()
        if role == Qt.DisplayRole:
            value = self._df.iloc[index.row(), index.column()]
            if isinstance(value, str):
                return value
            return str(value)
        elif role == Qt.BackgroundRole:
            if index.row() % 2 == 1:  # 짝수 행 (0부터 시작하므로 인덱스가 1,3,5,...)
                return QColor(240, 240, 240)  # 연한 회색
            else:
                return QVariant()
        return QVariant()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if self._df is None:
            return QVariant()
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self._df.columns[section])
            else:
                return str(section + 1)  # 행 번호를 1부터 시작하도록 설정
        return QVariant()


class JSONLViewer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JSONL Viewer")
        self.resize(1600, 1000)  # 창 크기를 더 넓게 설정

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # 상단 레이아웃 (로컬 및 원격 파일 로드)
        self.top_layout = QHBoxLayout()

        # 로컬 파일 로드 그룹박스
        self.local_group = QGroupBox("Local File")
        self.local_layout = QVBoxLayout()
        self.local_group.setLayout(self.local_layout)

        self.local_browse_button = QPushButton("Browse")
        self.local_browse_button.clicked.connect(self.browse_file)
        self.local_layout.addWidget(self.local_browse_button)

        self.local_path_input = QLineEdit()
        self.local_path_input.setPlaceholderText("Enter local file path here...")
        self.local_layout.addWidget(self.local_path_input)

        self.local_load_button = QPushButton("Load Local File")
        self.local_load_button.clicked.connect(self.load_local_file)
        self.local_layout.addWidget(self.local_load_button)

        self.top_layout.addWidget(self.local_group)

        # 원격 파일 로드 그룹박스
        self.remote_group = QGroupBox("Remote File (SSH)")
        self.remote_layout = QVBoxLayout()
        self.remote_group.setLayout(self.remote_layout)

        form_layout = QFormLayout()

        self.hostname_input = QLineEdit()
        self.hostname_input.setPlaceholderText("e.g., 1.2.3.4")
        form_layout.addRow("Hostname:", self.hostname_input)

        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("e.g., 22")
        self.port_input.setText("22")
        form_layout.addRow("Port:", self.port_input)

        self.username_input = QLineEdit()
        form_layout.addRow("Username:", self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        form_layout.addRow("Password:", self.password_input)

        self.remote_layout.addLayout(form_layout)

        self.remote_path_input = QLineEdit()
        self.remote_path_input.setPlaceholderText("Enter remote file path here...")
        self.remote_layout.addWidget(self.remote_path_input)

        self.remote_load_button = QPushButton("Load Remote File")
        self.remote_load_button.clicked.connect(self.load_remote_file)
        self.remote_layout.addWidget(self.remote_load_button)

        self.top_layout.addWidget(self.remote_group)

        self.layout.addLayout(self.top_layout)

        # 중간 테이블 뷰 (더 넓게 설정)
        self.table_view = QTableView()
        self.table_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_view.setWordWrap(True)
        self.table_view.setItemDelegate(MultiLineDelegate(self.table_view))
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.verticalHeader().setDefaultSectionSize(50)  # 초기 행 높이 설정
        self.table_view.setAlternatingRowColors(False)  # 직접 배경색 설정하므로 비활성화
        self.table_view.verticalHeader().setVisible(True)  # 행 번호 표시

        # 컨텍스트 메뉴 설정
        self.table_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.open_context_menu)

        self.layout.addWidget(self.table_view, stretch=8)  # 테이블 뷰에 더 많은 공간 할당

        # 페이징 레이아웃
        self.pagination_layout = QHBoxLayout()
        self.prev_button = QPushButton("Previous")
        self.prev_button.clicked.connect(self.prev_page)
        self.pagination_layout.addWidget(self.prev_button)

        self.page_label = QLabel("Page 1")
        self.pagination_layout.addWidget(self.page_label)

        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.next_page)
        self.pagination_layout.addWidget(self.next_button)

        # Rows per page
        self.rows_per_page_label = QLabel("Rows per page:")
        self.pagination_layout.addWidget(self.rows_per_page_label)

        self.rows_per_page_combo = QComboBox()
        self.rows_per_page_combo.addItems(['5', '10', '20', '50', '100'])
        self.rows_per_page_combo.setCurrentText('10')
        self.rows_per_page_combo.currentIndexChanged.connect(self.update_pagination)
        self.pagination_layout.addWidget(self.rows_per_page_combo)

        self.layout.addLayout(self.pagination_layout)

        # 하단 레이아웃 (컬럼 선택 및 pandas 명령어 입력) 축소
        self.bottom_layout = QHBoxLayout()

        # 컬럼 선택
        self.columns_layout = QVBoxLayout()
        self.columns_label = QLabel("Select Columns:")
        self.columns_layout.addWidget(self.columns_label)

        self.columns_list = QListWidget()
        self.columns_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.columns_list.setMaximumHeight(150)  # 높이 축소
        self.columns_layout.addWidget(self.columns_list)

        self.apply_columns_button = QPushButton("Apply Columns")
        self.apply_columns_button.clicked.connect(self.apply_columns)
        self.columns_layout.addWidget(self.apply_columns_button)

        self.bottom_layout.addLayout(self.columns_layout)

        # pandas 명령어 입력
        self.pandas_layout = QVBoxLayout()
        self.pandas_label = QLabel("Pandas Commands:")
        self.pandas_layout.addWidget(self.pandas_label)

        self.pandas_text = QTextEdit()
        self.pandas_text.setFixedHeight(80)  # 높이 축소
        self.pandas_layout.addWidget(self.pandas_text)

        # Apply Commands와 Reset Commands 버튼을 가로로 배치
        self.pandas_buttons_layout = QHBoxLayout()
        self.apply_pandas_button = QPushButton("Apply Commands")
        self.apply_pandas_button.clicked.connect(self.apply_pandas_commands)
        self.pandas_buttons_layout.addWidget(self.apply_pandas_button)

        self.reset_pandas_button = QPushButton("Reset Commands")
        self.reset_pandas_button.clicked.connect(self.reset_pandas_commands)
        self.pandas_buttons_layout.addWidget(self.reset_pandas_button)

        self.pandas_layout.addLayout(self.pandas_buttons_layout)

        self.bottom_layout.addLayout(self.pandas_layout)

        self.layout.addLayout(self.bottom_layout, stretch=2)  # 하단 레이아웃의 공간 축소

        # 데이터 관련 변수
        self.original_df = pd.DataFrame()
        self.display_df = pd.DataFrame()
        self.previous_display_df = pd.DataFrame()  # 이전 상태 저장용
        self.model = DataFrameModel(self.display_df)
        self.table_view.setModel(self.model)

        # 페이징 관련 변수
        self.current_page = 1
        self.rows_per_page = 10
        self.total_pages = 1

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open JSONL File", "", "JSONL Files (*.jsonl)")
        if file_path:
            self.local_path_input.setText(file_path)
            self.load_local_file()

    def load_local_file(self):
        file_path = self.local_path_input.text().strip()
        if not file_path:
            QMessageBox.warning(self, "Warning", "Please enter a local file path or use the Browse button.")
            return
        self.load_file(file_path, local=True)

    def load_remote_file(self):
        file_path = self.remote_path_input.text().strip()
        hostname = self.hostname_input.text().strip()
        port = self.port_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not (file_path and hostname and port and username and password):
            QMessageBox.warning(self, "Warning", "Please fill in all SSH and remote file path fields.")
            return

        try:
            port = int(port)
        except ValueError:
            QMessageBox.warning(self, "Warning", "Port must be an integer.")
            return

        creds = {
            'hostname': hostname,
            'port': port,
            'username': username,
            'password': password
        }

        self.load_file(file_path, local=False, creds=creds)

    def load_file(self, file_path, local=True, creds=None):
        try:
            if local:
                if not os.path.exists(file_path):
                    QMessageBox.critical(self, "Error", f"File does not exist: {file_path}")
                    return
                # 파일이 비어있는지 확인
                if os.path.getsize(file_path) == 0:
                    QMessageBox.warning(self, "Warning", "The selected file is empty.")
                    return
                df = pd.read_json(file_path, lines=True)
            else:
                df = self.read_remote_jsonl(file_path, creds)
                if df.empty:
                    QMessageBox.warning(self, "Warning", "The remote file is empty or could not be parsed.")
                    return

            self.original_df = df
            self.display_df = self.original_df.copy()
            self.previous_display_df = self.display_df.copy()  # 초기 상태 저장
            self.setup_columns()
            self.current_page = 1
            self.update_pagination()
            self.pandas_text.clear()  # 데이터 로드 시 pandas 명령어 초기화
        except ValueError as ve:
            QMessageBox.critical(self, "Error", f"JSON parsing error:\n{str(ve)}")
            print(f"JSON parsing error: {ve}", file=sys.stderr)
        except Exception as e:
            # 에러 메시지를 더 명확히 표시하고 로그에 출력
            QMessageBox.critical(self, "Error", f"Failed to load file:\n{str(e)}")
            print(f"Error loading file: {e}", file=sys.stderr)

    def read_remote_jsonl(self, path, creds):
        try:
            hostname = creds['hostname']
            port = creds['port']
            username = creds['username']
            password = creds['password']

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(hostname, port=port, username=username, password=password)

            sftp = ssh.open_sftp()
            try:
                with sftp.file(path, 'r') as remote_file:
                    lines = remote_file.readlines()
            except FileNotFoundError:
                QMessageBox.critical(self, "Error", f"Remote file does not exist: {path}")
                return pd.DataFrame()
            finally:
                sftp.close()
                ssh.close()

            # Decode bytes to string if necessary
            if lines and isinstance(lines[0], bytes):
                lines = [line.decode('utf-8') for line in lines]

            if not lines:
                # 파일이 비어있는 경우
                return pd.DataFrame()

            from io import StringIO
            data = ''.join(lines)
            df = pd.read_json(StringIO(data), lines=True)
            return df
        except paramiko.AuthenticationException:
            QMessageBox.critical(self, "Authentication Error", "SSH Authentication failed. Please check your credentials.")
            return pd.DataFrame()
        except paramiko.SSHException as e:
            QMessageBox.critical(self, "SSH Error", f"SSH connection failed:\n{str(e)}")
            return pd.DataFrame()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read remote file:\n{str(e)}")
            return pd.DataFrame()

    def setup_columns(self):
        self.columns_list.clear()
        for col in self.display_df.columns:
            item = QListWidgetItem(col)
            item.setSelected(True)
            self.columns_list.addItem(item)

    def apply_columns(self):
        selected_items = self.columns_list.selectedItems()
        selected_columns = [item.text() for item in selected_items]
        if not selected_columns:
            QMessageBox.warning(self, "Warning", "No columns selected. Displaying all columns.")
            self.display_df = self.original_df.copy()
        else:
            # 존재하지 않는 컬럼을 선택한 경우 예외 처리
            invalid_cols = [col for col in selected_columns if col not in self.original_df.columns]
            if invalid_cols:
                QMessageBox.warning(self, "Warning", f"The following columns do not exist and will be ignored:\n{', '.join(invalid_cols)}")
                selected_columns = [col for col in selected_columns if col in self.original_df.columns]
            self.display_df = self.original_df[selected_columns].copy()
        self.previous_display_df = self.display_df.copy()  # 상태 저장
        self.current_page = 1
        self.update_pagination()

    def apply_pandas_commands(self):
        commands = self.pandas_text.toPlainText()
        if not commands.strip():
            QMessageBox.warning(self, "Warning", "No commands entered.")
            return
        try:
            # pandas 명령어 적용 전 현재 상태 저장
            self.previous_display_df = self.display_df.copy()

            # 안전한 eval 환경 설정
            allowed_names = {"df": self.display_df, "pd": pd}
            result = eval(commands, {"__builtins__": {}}, allowed_names)
            if isinstance(result, pd.DataFrame):
                self.display_df = result
                self.setup_columns()
                self.current_page = 1
                self.update_pagination()
            else:
                QMessageBox.warning(self, "Warning", "The command did not return a DataFrame.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to execute commands:\n{str(e)}")
            print(f"Error executing pandas commands: {e}", file=sys.stderr)

    def reset_pandas_commands(self):
        if not self.previous_display_df.empty:
            self.display_df = self.previous_display_df.copy()
            self.setup_columns()
            self.current_page = 1
            self.update_pagination()
            self.pandas_text.clear()  # pandas 명령어 입력창 초기화
            QMessageBox.information(self, "Info", "Pandas commands have been reset to the previous state.")
        else:
            QMessageBox.warning(self, "Warning", "No previous state to revert to.")

    def reset_data(self):
        self.display_df = self.original_df.copy()
        self.previous_display_df = self.display_df.copy()  # 상태 저장
        self.setup_columns()
        self.current_page = 1
        self.update_pagination()
        self.pandas_text.clear()

    def update_pagination(self):
        try:
            self.rows_per_page = int(self.rows_per_page_combo.currentText())
            total_rows = len(self.display_df)
            self.total_pages = max(1, (total_rows + self.rows_per_page - 1) // self.rows_per_page)
            self.current_page = min(self.current_page, self.total_pages)
            self.show_page()
        except AttributeError as ae:
            QMessageBox.critical(self, "Pagination Error", f"Pagination error:\n{str(ae)}")
            print(f"Pagination AttributeError: {ae}", file=sys.stderr)
        except Exception as e:
            QMessageBox.critical(self, "Pagination Error", f"Pagination error:\n{str(e)}")
            print(f"Pagination error: {e}", file=sys.stderr)

    def show_page(self):
        try:
            start = (self.current_page - 1) * self.rows_per_page
            end = start + self.rows_per_page
            page_df = self.display_df.iloc[start:end]
            self.model.setDataFrame(page_df)
            self.table_view.resizeColumnsToContents()
            self.page_label.setText(f"Page {self.current_page} of {self.total_pages}")
            self.table_view.horizontalHeader().setStretchLastSection(True)
            self.table_view.resizeRowsToContents()  # 행 높이를 내용에 맞게 자동 조정
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to display page:\n{str(e)}")
            print(f"Error displaying page: {e}", file=sys.stderr)

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.show_page()

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.show_page()

    def open_context_menu(self, position: QPoint):
        indexes = self.table_view.selectedIndexes()
        if not indexes:
            return

        # Get selected rows and columns
        selected_rows = sorted(set(index.row() for index in indexes))
        selected_columns = sorted(set(index.column() for index in indexes))

        # Build JSON data
        json_data = []
        for row in selected_rows:
            row_data = {}
            for col in selected_columns:
                index = self.model.index(row, col)
                header = self.model.headerData(col, Qt.Horizontal, Qt.DisplayRole)
                value = self.model.data(index, Qt.DisplayRole)
                row_data[header] = value
            json_data.append(row_data)

        # Convert to JSON string
        # json_str = pd.json.dumps(json_data, ensure_ascii=False, indent=4)
        import json
        # json_str = json.dumps(json_data, ensure_ascii=False, indent=4)
        json_str = '\n'.join([json.dumps(item, ensure_ascii=False) for item in json_data])

        # Create context menu
        menu = QMenu()
        copy_action = menu.addAction("Copy as JSON")
        action = menu.exec_(self.table_view.viewport().mapToGlobal(position))
        if action == copy_action:
            clipboard = QApplication.clipboard()
            clipboard.setText(json_str)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    viewer = JSONLViewer()
    viewer.show()
    sys.exit(app.exec_())
