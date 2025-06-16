import configparser
import os

class Parser:
    def __init__(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_file = os.path.join(current_dir, 'config.ini')

        if not os.path.exists(self.config_file):
            parent_dir = os.path.dirname(current_dir)
            self.config_file = os.path.join(parent_dir, 'config.ini')

        self.config = self.load_config()

    def load_config(self):
        config = configparser.ConfigParser()
        if os.path.exists(self.config_file):
            config.read(self.config_file)
        else:
            raise FileNotFoundError(f"Config file not found: {self.config_file}")
        return config

    def return_var(self, section, option):
        """
        Returns a value from config.ini

        :param section:
        :param option:
        :return:
            str: every value is returned as a string or list of strings
        """
        return self.config.get(section, option)

    def return_list(self, section, option, annotation):
        match annotation:
            case "int":
                value = self.config.get(section, option)
                return [int(item.strip()) for item in value.split(',')]
            case "str":
                value = self.config.get(section, option)
                return [item.strip() for item in value.split(',')]