from PyQt6 import QtWidgets, QtCore
from core.uploader import validate_login, validate_oauth_login
from core import credential_storage


class AuthDialog(QtWidgets.QDialog):
    """Dialog for entering Wikidata credentials and testing them.

    Supports two authentication methods:
      - Bot password (username + password)
      - OAuth 1.0a (consumer key/secret + access token/secret)
    The selected method determines which fields are shown.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wikidata Bot Login")
        self.setModal(True)
        self.resize(400, 250)
        self.login_successful = False
        self.credentials = None  # tuple of credentials based on auth method
        self.login_object = None  # wdi_login.WDLogin instance
        self._create_ui()
        self._load_stored_credentials()

    def _create_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # OAuth selection checkbox
        self.use_oauth_checkbox = QtWidgets.QCheckBox("Use OAuth 1.0a")
        self.use_oauth_checkbox.toggled.connect(self._on_oauth_toggled)
        layout.addWidget(self.use_oauth_checkbox)

        # Stacked widget to swap between credential forms
        self.stacked = QtWidgets.QStackedWidget()

        # --- Bot password page ---
        bot_page = QtWidgets.QWidget()
        bot_form = QtWidgets.QFormLayout(bot_page)
        self.username_edit = QtWidgets.QLineEdit()
        self.username_edit.setPlaceholderText("Bot username")
        bot_form.addRow("Username:", self.username_edit)

        self.password_edit = QtWidgets.QLineEdit()
        self.password_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Bot password")
        bot_form.addRow("Password:", self.password_edit)
        self.stacked.addWidget(bot_page)

        # --- OAuth 1.0a page ---
        oauth_page = QtWidgets.QWidget()
        oauth_form = QtWidgets.QFormLayout(oauth_page)

        self.consumer_key_edit = QtWidgets.QLineEdit()
        self.consumer_key_edit.setPlaceholderText("Consumer key")
        oauth_form.addRow("Consumer key:", self.consumer_key_edit)

        self.consumer_secret_edit = QtWidgets.QLineEdit()
        self.consumer_secret_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.consumer_secret_edit.setPlaceholderText("Consumer secret")
        oauth_form.addRow("Consumer secret:", self.consumer_secret_edit)

        self.access_token_edit = QtWidgets.QLineEdit()
        self.access_token_edit.setPlaceholderText("Access token")
        oauth_form.addRow("Access token:", self.access_token_edit)

        self.access_secret_edit = QtWidgets.QLineEdit()
        self.access_secret_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.access_secret_edit.setPlaceholderText("Access secret")
        oauth_form.addRow("Access secret:", self.access_secret_edit)

        self.stacked.addWidget(oauth_page)
        layout.addWidget(self.stacked)

        # Remember credentials option
        self.remember_checkbox = QtWidgets.QCheckBox("Remember credentials on this device")
        layout.addWidget(self.remember_checkbox)

        # Button row
        button_layout = QtWidgets.QHBoxLayout()
        self.test_button = QtWidgets.QPushButton("Test Login")
        self.test_button.clicked.connect(self._test_login)
        button_layout.addWidget(self.test_button)

        self.ok_button = QtWidgets.QPushButton("OK")
        self.ok_button.setEnabled(False)
        self.ok_button.clicked.connect(self.accept)
        button_layout.addWidget(self.ok_button)

        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.status_label = QtWidgets.QLabel("Enter your credentials. Select OAuth if you have OAuth tokens.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Initialize with bot password page visible
        self.stacked.setCurrentIndex(0)

    def _on_oauth_toggled(self, checked):
        """Switch between bot password and OAuth forms."""
        self.stacked.setCurrentIndex(1 if checked else 0)
        self.status_label.setText(
            "Enter your OAuth consumer and access tokens." if checked
            else "Enter your bot username and password."
        )

    def _test_login(self):
        """Validate credentials using the selected authentication method."""
        self.status_label.setText("Testing login...")
        self.test_button.setEnabled(False)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)

        try:
            if self.use_oauth_checkbox.isChecked():
                consumer_key = self.consumer_key_edit.text().strip()
                consumer_secret = self.consumer_secret_edit.text()
                access_token = self.access_token_edit.text().strip()
                access_secret = self.access_secret_edit.text()

                if not all([consumer_key, consumer_secret, access_token, access_secret]):
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Missing Credentials",
                        "Please fill in all OAuth fields."
                    )
                    return

                login = validate_oauth_login(
                    consumer_key,
                    consumer_secret,
                    access_token,
                    access_secret
                )
                self.credentials = (consumer_key, consumer_secret, access_token, access_secret)
            else:
                username = self.username_edit.text().strip()
                password = self.password_edit.text()

                if not username or not password:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Missing Credentials",
                        "Please enter both username and password."
                    )
                    return

                login = validate_login(username, password)
                self.credentials = (username, password)

        except Exception as e:
            login = None
            error_msg = str(e)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
            self.test_button.setEnabled(True)

        if login is not None:
            self.login_successful = True
            self.login_object = login
            self.ok_button.setEnabled(True)
            self.status_label.setText("Login successful. Click OK to continue.")
        else:
            self.login_successful = False
            self.ok_button.setEnabled(False)
            self.status_label.setText("Login failed. Check your credentials.")

    def get_login_object(self):
        """Return the WDLogin object if login was successful."""
        if self.login_successful:
            return self.login_object
        return None

    def accept(self):
        """Save credentials if requested, then accept the dialog."""
        if self.remember_checkbox.isChecked():
            self._save_credentials_from_fields()
        super().accept()

    def _load_stored_credentials(self):
        """Load saved credentials and pre-fill the form."""
        creds = credential_storage.load_credentials()
        if not creds:
            return

        if creds.get('type') == 'oauth':
            self.use_oauth_checkbox.setChecked(True)
            self.consumer_key_edit.setText(creds.get('consumer_key', ''))
            self.consumer_secret_edit.setText(creds.get('consumer_secret', ''))
            self.access_token_edit.setText(creds.get('access_token', ''))
            self.access_secret_edit.setText(creds.get('access_secret', ''))
        else:
            self.use_oauth_checkbox.setChecked(False)
            self.username_edit.setText(creds.get('username', ''))
            self.password_edit.setText(creds.get('password', ''))

        self.remember_checkbox.setChecked(True)

    def _save_credentials_from_fields(self):
        """Collect current fields and save encrypted credentials."""
        if self.use_oauth_checkbox.isChecked():
            consumer_key = self.consumer_key_edit.text().strip()
            consumer_secret = self.consumer_secret_edit.text()
            access_token = self.access_token_edit.text().strip()
            access_secret = self.access_secret_edit.text()
            if not all([consumer_key, consumer_secret, access_token, access_secret]):
                return
            creds = {
                'type': 'oauth',
                'consumer_key': consumer_key,
                'consumer_secret': consumer_secret,
                'access_token': access_token,
                'access_secret': access_secret,
            }
        else:
            username = self.username_edit.text().strip()
            password = self.password_edit.text()
            if not username or not password:
                return
            creds = {
                'type': 'bot',
                'username': username,
                'password': password,
            }
        credential_storage.save_credentials(creds)
