import os
import sys
import shutil
import threading
import pandas as pd
from random import randint
from PyQt5 import QtGui
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QComboBox, QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar, QMessageBox
# imports script.py, used for creating plots
import script
import fileConfig
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, when

# Initialize Spark session
spark = SparkSession.builder.appName("F1TelemetryApp").getOrCreate()

# Read data from HDFS
events = spark.read.csv("hdfs:///path/to/events.csv", header=True, inferSchema=True)
drivers = spark.read.csv("hdfs:///path/to/drivers.csv", header=True, inferSchema=True)
race_laps = spark.read.csv("hdfs:///path/to/race_laps.csv", header=True, inferSchema=True)

# Convert Spark DataFrames to Pandas for GUI compatibility
events_pd = events.toPandas()
drivers_pd = drivers.toPandas()
race_laps_pd = race_laps.toPandas()

placeholder_path = fileConfig.PLACEHOLDER_IMG

# active race years
year = events_pd.columns
year = year[1:len(year)].to_list()
year.insert(0, 'Select Year')

# values for dropdown labels
driver_name = drivers_pd
location = ['Select Location']
session = ['Race', 'Qualifying', 'FP1', 'FP2', 'FP3']  # 'Sprint Qualifying', 'Sprint' : removed until data is consistent
driver_name = ['Select Driver']
analysis_type = ['Lap Time', 'Fastest Lap', 'Fastest Sectors', 'Full Telemetry']

# stylesheet for progress bar
StyleSheet = '''
#RedProgressBar {
    min-height: 12px;
    max-height: 12px;
    border-radius: 2px;
    border: .5px solid #808080;;
}
#RedProgressBar::chunk {
    border-radius: 2px;
    background-color: #DC0000;
    opacity: 1;
}
.warning-text {
    color:#DC0000
}
'''

# defines progressbar
class ProgressBar(QProgressBar):
    def __init__(self, *args, **kwargs):
        super(ProgressBar, self).__init__(*args, **kwargs)
        self.setValue(0)
        if self.minimum() != self.maximum():
            self.timer = QTimer(self, timeout=self.onTimeout)
            self.timer.start(randint(1, 3) * 1000)

    def onTimeout(self):
        if self.value() >= 100:
            self.timer.stop()
            self.timer.deleteLater()
            del self.timer
            return
        self.setValue(self.value() + 1)

# main gui window 
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.UIComponents()

    def initUI(self):
        self.setFixedSize(880, 525)
        self.move(200, 100)
        self.setWindowTitle('Formula 1 Telemetry Analytics')
        self.setWindowIcon(QtGui.QIcon(os.path.join(fileConfig.IMG_DIR, 'f1.png')))

    def UIComponents(self):
        options_layout = QVBoxLayout()
        img_layout = QHBoxLayout()
        img_layout.addLayout(options_layout)  # two layouts to allow split screen view

        self.drop_year = QComboBox()
        self.drop_grand_prix = QComboBox()
        self.drop_session = QComboBox()
        self.drop_driver1 = QComboBox()
        self.drop_driver2 = QComboBox()
        self.drop_analysis = QComboBox()
        self.lap_number = QComboBox()

        self.warning_box = QMessageBox(self)
        self.warning_box.setWindowTitle('Error!')
        self.warning_box.setText('Select a valid race year.')
        self.warning_box.setDefaultButton(QMessageBox.Ok)

        label_year = QLabel('<span style="font-size:8.5pt; font-weight: 500"> Year: </span>')
        label_prix = QLabel('<span style="font-size:8.5pt; font-weight: 500"> Grand Prix Location: </span>')
        label_session = QLabel('<span style="font-size:8.5pt; font-weight: 500"> Session: </span>')
        label_d1 = QLabel('<span style="font-size:8.5pt; font-weight: 500"> Driver 1: </span>')
        label_d2 = QLabel('<span style="font-size:8.5pt; font-weight: 500"> Driver 2: </span>')
        label_analysis = QLabel('<span style="font-size:8.5pt; font-weight: 500"> Analysis Type: </span>')

        self.run_button = QPushButton('Run Analysis')
        self.save_button = QPushButton('Save Plot to Desktop')

        self.pbar = ProgressBar(self, minimum=0, maximum=0, textVisible=False,
                                objectName="RedProgressBar")

        self.drop_year.addItems(year)
        self.drop_grand_prix.addItems(location)
        self.drop_session.addItems(session)
        self.drop_driver1.addItems(driver_name)
        self.drop_driver2.addItems(driver_name)
        self.drop_analysis.addItems(analysis_type)

        options_layout.addWidget(label_year)
        options_layout.addWidget(self.drop_year)
        options_layout.addWidget(label_prix)
        options_layout.addWidget(self.drop_grand_prix)
        options_layout.addWidget(label_session)
        options_layout.addWidget(self.drop_session)
        options_layout.addWidget(label_d1)
        options_layout.addWidget(self.drop_driver1)
        options_layout.addWidget(label_d2)
        options_layout.addWidget(self.drop_driver2)
        options_layout.addWidget(label_analysis)
        options_layout.addWidget(self.drop_analysis)
        options_layout.addWidget(self.lap_number)
        self.lap_number.hide()
        options_layout.addWidget(self.pbar)
        self.pbar.hide()
        options_layout.addWidget(self.run_button)
        options_layout.addWidget(self.save_button)
        self.save_button.hide()

        options_layout.addStretch()

        self.drop_year.currentTextChanged.connect(self.update_lists)
        self.run_button.clicked.connect(self.thread_script)
        self.save_button.clicked.connect(self.save_plot)
        self.drop_analysis.currentTextChanged.connect(self.add_laps)
        self.drop_grand_prix.currentTextChanged.connect(self.update_laps)

        self.img_plot = QLabel()
        self.img_plot.setPixmap(QPixmap(placeholder_path).scaledToWidth(625))
        img_layout.addWidget(self.img_plot)

        self.setLayout(img_layout)

    def current_text(self):
        input_data = []
        text = self.drop_year.currentText()
        input_data.append(text)
        text = self.drop_grand_prix.currentText()
        input_data.append(text)
        text = self.drop_session.currentText()
        input_data.append(text)
        text = self.drop_driver1.currentText()
        input_data.append(text)
        text = self.drop_driver2.currentText()
        input_data.append(text)
        text = self.drop_analysis.currentText()
        input_data.append(text)
        text = self.lap_number.currentText()
        input_data.append(text)
        return input_data

    def display_plot(self, plot_path):
        self.img_plot.setPixmap(QPixmap(plot_path).scaledToWidth(625))

    def save_plot(self):
        desktop_path = os.path.join(os.path.join(os.environ['USERPROFILE']), 'Desktop')
        shutil.copy(self.plot_path, desktop_path)

    def add_laps(self):
        if self.drop_analysis.currentText() == 'Fastest Sectors':
            self.lap_number.show()
        else:
            self.lap_number.hide()

    def update_laps(self):
        if self.drop_grand_prix.currentText() != '':
            self.lap_number.clear()
            lap_val = ['Select Lap']
            race = self.drop_grand_prix.currentText()
            total_laps = race_laps_pd.loc[race_laps_pd.event == race, 'laps'].values[0]
            lap_val.extend(range(1, total_laps + 1))
            lap_val = map(str, lap_val)
            self.lap_number.addItems(lap_val)

    def thread_script(self):
        thread_script = threading.Thread(target=self.button_listen)
        thread_script.start()

    def button_listen(self):
        input_data = self.current_text()
        if input_data[0] == 'Select Year':
            self.run_button.setText('Run Analysis (Select Valid Year)')
        else:
            self.run_button.setText('Running . . .')
            self.save_button.hide()
            self.pbar.show()
            script.get_race_data(input_data, spark)  # Pass spark session to script
            self.plot_path = os.path.join(fileConfig.PLOT_DIR, f"{input_data[5]}.png")
            self.display_plot(self.plot_path)
            self.pbar.hide()
            self.run_button.setText('Run New Analysis')
            self.save_button.show()

    def update_lists(self):
        sel_year = self.drop_year.currentText()
        if sel_year != 'Select Year':
            self.drop_grand_prix.clear()
            self.drop_driver1.clear()
            self.drop_driver2.clear()
            
            # Use Spark to filter and collect data
            events_filtered = events.filter(col(str(sel_year)).isNotNull()).select(str(sel_year)).collect()
            drivers_filtered = drivers.filter(col(str(sel_year)).isNotNull()).select(str(sel_year)).collect()
            
            self.drop_grand_prix.addItems([row[str(sel_year)] for row in events_filtered])
            self.drop_driver1.addItems([row[str(sel_year)] for row in drivers_filtered])
            self.drop_driver2.addItems([row[str(sel_year)] for row in drivers_filtered])

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet(StyleSheet)
    mw = MainWindow()
    mw.show()
    sys.exit(app.exec_())
