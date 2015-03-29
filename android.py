import sublime
import sublime_plugin
import subprocess
import os
import fnmatch
import re
import json
import time

from Default.exec import ExecCommand
import platform

scriptpath = os.path.sep.join([os.path.dirname(os.path.abspath(__file__)), ""])
platform = sublime.platform() #Stopped working in sublime text 3 beta (fixed in build 3011)
#platform = platform.system().lower().replace('darwin', 'osx')

adb_bin = os.path.sep.join(["platform-tools","adb"])
logcat_script = "logcat"
run_script = "run"
android_bin = os.path.sep.join(["tools", "android"])
ddms_bin = os.path.sep.join(["tools", "ddms"])
ant_bin = "ant"
java_bin = os.path.sep.join(["bin","java"])
if platform == 'windows' :
    adb_bin += ".exe"
    logcat_script += ".bat"
    run_script += ".bat"
    android_bin += ".bat"
    ddms_bin += ".bat"
    ant_bin += ".bat"
    java_bin += ".exe"
else:
    logcat_script += ".sh"
    run_script += ".sh"

args = {
            'windows': "Android (Windows).sublime-settings",
            'osx': "Android (OSX).sublime-settings",
            'linux': "Android (Linux).sublime-settings"
        }
settings_file = args[platform]

#TODO: Clean this up
def getBuiltTargets():
    targets = []
    settings = AndroidSettings(sublime.load_settings(settings_file))
    if not settings.is_valid():
        return
    if platform == 'windows' :
        si = subprocess.STARTUPINFO()
        si.dwFlags = subprocess.STARTF_USESTDHANDLES | subprocess.STARTF_USESHOWWINDOW
    else:
        si = None
    sdk = settings.sdk
    proc = subprocess.Popen([sdk + android_bin, "list", "target", "-c"], shell=False, stdout=subprocess.PIPE, startupinfo=si)
    output = proc.stdout.read().decode('utf-8')
    proc.communicate()
    targets = output.split('\n')
    if targets is None:
        sublime.status_message( "Error: No android targets installed!" )
        sublime.message_dialog( "No android targets installed.\n\n" +
                "Please run  Android/SDK Tools/Launch SDK Manager\n" +
                "and install a \"SDK Platform\"." )
        return False
    return targets

#TODO: Check if java and ant is installed.
#TODO: Check if android project (build.xml and AndroidManifest.xml) else disable plugin

class AndroidSettings():
    ant = ""
    jdk = ""
    sdk = ""
    debug = True
    compile_on_save = True
    run_on_device = True

    def __init__(self, settings):
        # Get ANT and JAVA locations from settings OR environment variables.
        self.ant =  os.path.normcase(settings.get("ant_bin"))
        if "ANT_HOME" in os.environ and os.environ["ANT_HOME"] != "" and self.ant is None:
            self.ant = os.path.normcase(os.environ["ANT_HOME"] + os.path.sep + "bin")
        if not self.ant.endswith(os.path.sep): self.ant += os.path.sep

        self.jdk = os.path.normcase(settings.get("jdk_bin"))
        if "JAVA_HOME" in os.environ and os.environ["JAVA_HOME"] != "" and self.jdk is None:
            self.jdk = os.path.normcase(os.environ["JAVA_HOME"])
        if not self.jdk.endswith(os.path.sep): self.jdk += os.path.sep

        self.sdk = os.path.normcase(settings.get("android_sdk"))
        if not self.sdk.endswith(os.path.sep): self.sdk += os.path.sep

        self.default_android_project_dir = settings.get("default_android_project_dir")
        self.debug = settings.get("debug")
        self.compile_on_save = settings.get("compile_on_save")
        self.run_on_device = settings.get("run_on_device")

    def is_valid(self):
        if self.ant is None or self.sdk is None or self.jdk is None:
            sublime.error_message( "Error: Path settings are incorrect.\n\nPlease set the correct path in Android/Preferences." )
            return False

        if not (os.path.exists(self.ant) and os.path.isfile(self.ant + ant_bin)):
            sublime.error_message( "Error: Apache Ant path is incorrect.\n\nPlease set the correct path in Android/Preferences." )
            return False

        if not (os.path.exists(self.jdk) and os.path.isfile(self.jdk + java_bin)):
            sublime.error_message( "Error: JDK path is incorrect.\n\nPlease set the correct path in Android/Preferences." )
            return False

        if not (os.path.exists(self.sdk) and os.path.isfile(self.sdk + adb_bin) and os.path.isfile(self.sdk + android_bin)):
            sublime.error_message( "Error: Android SDK path is incorrect.\n\nPlease set the correct path in Android/Preferences" )
            return False
        return True

class AndroidNewProjectCommand(sublime_plugin.WindowCommand):
    project_name = ""
    activity_name = ""
    package_name = ""
    project_path = ""
    build_target = ""
    targets = []
    settings = []

    def run(self):
        self.settings = AndroidSettings(sublime.load_settings(settings_file))
        if not self.settings.is_valid():
            return
        self.window.show_input_panel("Project name:", "", self.on_project_name_input, None, None)

    def on_project_name_input(self, text):
        if len(text) < 2:
            self.window.show_input_panel("Project name: Name too short!", "", self.on_project_name_input, None, None)
        else:
            if re.match('^[a-zA-Z0-9_]*$', text):
                self.project_name = text
                self.window.show_input_panel("Activity name:", self.project_name.lower(), self.on_activity_name_input, None, None)
            else:
                self.window.show_input_panel("Project name: Allowed characters are: a-z A-Z 0-9 _", "", self.on_project_name_input, None, None)

    def on_activity_name_input(self, text):
        self.activity_name = text
        self.window.show_input_panel("Package name:", "com." + self.project_name.lower(), self.on_package_name_input, None, None)

    def on_package_name_input(self, text):
        self.package_name = text
        android_projects = self.settings.default_android_project_dir
        default_text = ""
        if not android_projects is None:
            default_text = android_projects + os.path.sep + self.project_name
        self.window.show_input_panel("Project path:", default_text, self.on_path_input, None, None)

    def on_path_input(self, text):
        self.project_path = text
        self.targets = getBuiltTargets()
        self.window.show_quick_panel(self.targets, self.on_target_selected)

    def on_target_selected(self, picked):
        if picked == -1:
            g = (i for i in self.targets if i.startswith("android")) # use "Google" for google api
            match = list(g)
            if match:
                target  =  match[0]
            else:
                target  =  self.targets[0]
            self.window.show_input_panel("Build target:", target, self.on_target_set, None, None)
        else:
            self.on_target_set(self.targets[picked])

    def on_target_set(self, target):
        if target == "":
            sublime.status_message( "Error: No android target selected!" )
            self.window.show_quick_panel(self.targets, self.on_target_selected)
        else:
            self.build_target = str(target)
            self.create_project()

    def create_project(self):
        self.window.run_command("show_panel", {"panel": "console"})
        ant = self.settings.ant
        sdk = self.settings.sdk
        jdk = self.settings.jdk
        print("Creating project (%s)" % self.project_path)

        # Create folder containing the project
        if not os.path.exists(self.project_path):
            os.makedirs(self.project_path)

        # Call android SDK to setup a new project
        args = {
            "cmd": [sdk + android_bin,
            "create", "project",
             "--target", self.build_target,
             "--name", self.project_name,
             "--path", self.project_path,
             "--activity", self.activity_name,
             "--package", self.package_name],

            "env": {"JAVA_HOME": jdk},

            "path": os.environ["PATH"] +
                os.pathsep + ant +
                os.pathsep + jdk +
                os.pathsep + sdk + "tools" + os.path.sep +
                os.pathsep + sdk + "platform-tools" + os.path.sep
        }
        self.window.run_command("exec", args)

        new_project  = "{\n"
        new_project += "    \"folders\":\n"
        new_project += "    [\n"
        new_project += "        {\n"
        new_project += "            \"path\": \".\",\n"
        new_project += "            \"name\": \"%s\",\n" % self.project_name
        new_project += "            \"folder_exclude_patterns\": [],\n"
        new_project += "            \"file_exclude_patterns\": [\"*.sublime-project\", \"*.sublime-workspace\"]\n"
        new_project += "        }\n"
        new_project += "    ]\n"
        new_project += "}"
        project_file = os.path.sep.join([self.project_path, "%s.sublime-project" % self.project_name])
        with open(project_file, 'w') as file:
            file.write(new_project)
        #TODO: Fix opening the project.
        self.window.run_command('open_project', [project_file])
        sublime.active_window().open_file(project_file)

        self.window.new_file().run_command('android_show_readme', {"path": self.project_path})
        self.window.run_command('set_build_system', {"file": "Packages/Android/Android.sublime-build"})

class AndroidShowReadmeCommand(sublime_plugin.TextCommand):
    def run(self, edit, path = ""):
        self.view.set_name("readme.txt")
        self.view.settings().set("default_dir", path)
        self.view.insert(edit, 0, readme) # See at the bottom for the readme
        self.view.show(0)

class AndroidImportProjectCommand(sublime_plugin.WindowCommand):
    project_path = ""
    project_name = ""
    def run(self):
        self.window.run_command('prompt_open_folder')

        #   check for AndroidManifest.xml
        folder = sublime.active_window().folders()[0]
        self.project_path = self.locatePath("AndroidManifest.xml", folder)

        #check if android project (exclude the binary folder)
        if os.path.isfile(self.project_path + os.path.sep + "AndroidManifest.xml") and \
                not re.search(os.path.sep + "bin", self.project_path):
            self.settings = AndroidSettings(sublime.load_settings(settings_file))
            if not self.settings.is_valid():
                return

            # get app name from AndroidManifest.xml
            self.project_name = self.findActivity(self.project_path + os.path.sep + "AndroidManifest.xml").replace('.', '')

            # create a new sublime project file with appname and add folder
            new_project  = "{\n"
            new_project += "    \"folders\":\n"
            new_project += "    [\n"
            new_project += "        {\n"
            new_project += "            \"path\": \".\",\n"
            new_project += "            \"name\": \"%s\",\n" % self.project_name
            new_project += "            \"folder_exclude_patterns\": [],\n"
            new_project += "            \"file_exclude_patterns\": [\"*.sublime-project\", \"*.sublime-workspace\"]\n"
            new_project += "        }\n"
            new_project += "    ]\n"
            new_project += "}"
            project_file = os.path.sep.join([self.project_path, "%s.sublime-project" % self.project_name])
            with open(project_file, 'w') as file:
                file.write(new_project)
            #TODO: Fix opening the project.
            self.window.run_command('open_project', [project_file])
            sublime.active_window().open_file(project_file)

            # show readme
            self.window.run_command('android_show_readme', {"path": self.project_path})
            self.window.run_command('set_build_system', {"file": "Packages/Android/Android.sublime-build"})
            return
        # else error dialog no AndroidManifest.xml not found
        sublime.error_message( "Error: No android project found.\n\nAndroidManifest.xml not found." )

        return

    def findActivity(self, xmlFile):
        if not os.path.isfile(xmlFile):
            return
        file = open(xmlFile, 'r')
        lines = file.readlines()
        for line in lines:
            match = re.search("^\s*android:name=\"([\.a-zA-Z1-9]+)\"", line)
            if match:
                return match.group(1)

    def locatePath(self, pattern, root=os.curdir):
        for path, dirs, files in os.walk(os.path.abspath(root)):
            for filename in fnmatch.filter(files, pattern):
                return path


class AndroidOpenSdkCommand(sublime_plugin.WindowCommand):
    settings = []
    def run(self):
        self.settings = AndroidSettings(sublime.load_settings(settings_file))
        if not self.settings.is_valid():
            return
        if platform == 'windows' :
            subprocess.Popen([self.settings.sdk + android_bin, "sdk"], creationflags=0x08000000, shell=False)
        else:
            subprocess.Popen([self.settings.sdk + android_bin, "sdk"], shell=False)

class AndroidOpenAvdCommand(sublime_plugin.WindowCommand):
    settings = []
    def run(self):
        self.settings = AndroidSettings(sublime.load_settings(settings_file))
        if not self.settings.is_valid():
            return
        if platform == 'windows' :
            subprocess.Popen([self.settings.sdk + android_bin, "avd"], creationflags=0x08000000, shell=False)
        else:
            subprocess.Popen([self.settings.sdk + android_bin, "avd"], shell=False)

class AndroidOpenDdmsCommand(sublime_plugin.WindowCommand):
    settings = []
    def run(self):
        self.settings = AndroidSettings(sublime.load_settings(settings_file))
        if not self.settings.is_valid():
            return
        if platform == 'windows' :
            subprocess.Popen([self.settings.sdk + ddms_bin], creationflags=0x08000000, shell=False)
        else:
            subprocess.Popen([self.settings.sdk + ddms_bin], shell=False)

class AndroidBuildDebugCommand(sublime_plugin.WindowCommand):
    def run(self):
        settings = sublime.load_settings(settings_file)
        debug = settings.get('debug')
        if debug == True:
            settings.set('debug', False)
        else:
            settings.set('debug', True)
        sublime.save_settings(settings_file)
    def is_checked(self):
        settings = sublime.load_settings(settings_file)
        debug = settings.get('debug', False)
        if debug == True:
            return True
        else:
            return False

class AndroidBuildOnSaveCommand(sublime_plugin.WindowCommand):
    def run(self):
        settings = sublime.load_settings(settings_file)
        compile_on_save = settings.get('compile_on_save')
        if compile_on_save == True:
            settings.set('compile_on_save', False)
        else:
            settings.set('compile_on_save', True)
        sublime.save_settings(settings_file)
    def is_checked(self):
        settings = sublime.load_settings(settings_file)
        compile_on_save = settings.get('compile_on_save', False)
        if compile_on_save == True:
            return True
        else:
            return False

class AndroidRunOnDeviceCommand(sublime_plugin.WindowCommand):
    def run(self):
        settings = sublime.load_settings(settings_file)
        run_on_device = settings.get('run_on_device')
        if run_on_device == True:
            settings.set('run_on_device', False)
        else:
            settings.set('run_on_device', True)
        sublime.save_settings(settings_file)
    def is_checked(self):
        settings = sublime.load_settings(settings_file)
        run_on_device = settings.get('run_on_device', False)
        if run_on_device == True:
            return True
        else:
            return False

# Compiles code and builds a signed, debug/release package
class AndroidBuildCommand(sublime_plugin.WindowCommand):
    settings = []
    targets = []
    cmd = []
    path = ""
    build_target = ""
    quiet = False
    run_on_device = True

    def run(self, cmd = [], file_regex = "", line_regex = "", working_dir = "",
            encoding = "utf-8", env = {}, quiet = False, kill = False,
            # Catches "path" and "shell"
            **kwargs):

        path = working_dir
        if os.path.isfile(working_dir + os.path.sep + "AndroidManifest.xml"):
            self.path = working_dir
        else:
            for folder in self.window.folders():
                path = self.locatePath("AndroidManifest.xml", folder)
                if path is not None:
                   self.path = path

        #check if android project
        if os.path.isfile(self.path + os.path.sep + "AndroidManifest.xml"):
            self.settings = AndroidSettings(sublime.load_settings(settings_file))
            if not self.settings.is_valid():
                return
            self.path = path
            self.quiet = quiet
            self.run_on_device = self.settings.run_on_device
            self.checkBuildXML()

    def runQuiet(self):
        self.settings = AndroidSettings(sublime.load_settings(settings_file))
        if not self.settings.is_valid():
            return
        self.quiet = True
        self.run_on_device = False
        self.checkBuildXML()

    def checkBuildXML(self):
        for folder in self.window.folders():
            buildxml = self.locatePath("build.xml", folder)
            if buildxml is not None:
                self.path = buildxml
        # Checks for build.xml and if needed generates it
        if not os.path.isfile(self.path + os.path.sep + "build.xml"):
            if sublime.ok_cancel_dialog("The file build.xml doesn't exist and needs to be\n" +
                                        "created for ant to run.\n\n" +
                                        "Do you want it to be created automatically?"):
                if self.build_target == "": #TODO: Check the properties file.
                    self.targets = getBuiltTargets()
                    self.window.show_quick_panel(self.targets, self.selectedBuildTarget)
                else:
                    self.createBuildXML()
        else:
            self.build()

    def selectedBuildTarget(self, picked):
        if picked == -1:
            g = (i for i in self.targets if i.startswith("android")) # use "Google" for defaulting to google api
            match = list(g)
            if match:
                target  =  match[0]
            else:
                target  =  self.targets[0]
            self.window.show_input_panel("Build target:", target, self.setBuildTarget, None, None)
        else:
            self.setBuildTarget(self.targets[picked])

    def setBuildTarget(self, target):
        if target == "":
            sublime.status_message( "Error: No android target selected!" )
            self.window.show_quick_panel(self.targets, self.selectedBuildTarget)
        else:
            self.build_target = str(target)
            self.createBuildXML()

    def createBuildXML(self):
        # Call android SDK to update the project
        # args = {
        #     "cmd": [self.settings.sdk + android_bin,
        #     "update", "project",
        #     "--target", "\"%s\""%self.build_target,
        #     "--path", self.path]
        # }
        # self.window.run_command("exec", args)
        self.cmd = [self.settings.sdk + android_bin,
            "update", "project",
            "--target", "\"%s\"" % self.build_target,
            "--path", "\"%s\"" % self.path]
        self.build()

    def build(self):
        ant = self.settings.ant
        sdk = self.settings.sdk
        jdk = self.settings.jdk
        debug = self.settings.debug
        run_on_device = self.run_on_device

        buildxml = self.path + os.path.sep + "build.xml"
        manifest = self.path + os.path.sep + "AndroidManifest.xml"
        projectName = self.findProject(buildxml)
        package = self.findPackage(manifest)
        activity = self.findActivity(manifest)

        if package is None and activity is None:
            return
        component = package + "/" + activity

        if run_on_device and not debug:
            # Check for certificate before build & install in release mode
            properties = self.path + os.path.sep + "local.properties"
            keystore = self.findKeystore(properties)
            if keystore is None or not os.path.isfile(self.path + os.path.sep + keystore) and not os.path.isfile(keystore):
                sublime.message_dialog( "You need to generate a certificate first for signing and installing in release mode!" )
                return

        cmd = []
        if self.cmd:
            cmd.extend(self.cmd)
            cmd.append("&&")
        if run_on_device:
            cmd.extend([ant_bin, "uninstall"])
            cmd.append("&&")
        if debug:
            cmd.extend([ant_bin, "debug"])
        else:
            cmd.extend([ant_bin, "release"])
        if run_on_device:
            cmd.append("install")
            cmd.append("&&")
            cmd.extend(["adb", "shell", "am", "start", "-a", "android.intent.action.MAIN", "-n", component])

        args = {
            "cmd": [scriptpath + run_script] + cmd,
            "working_dir": self.path,

            "env": {"JAVA_HOME": jdk},

            "path": os.environ["PATH"] +
                    os.pathsep + ant +
                    os.pathsep + jdk +
                    os.pathsep + sdk + "tools" + os.path.sep +
                    os.pathsep + sdk + "platform-tools" + os.path.sep,

            "quiet": self.quiet
        }
        self.window.run_command("android_exec", args)
        if self.quiet:
            sublime.active_window().run_command("hide_panel")

    def findProject(self, xmlFile):
        if not os.path.isfile(xmlFile):
            return
        file = open(xmlFile, 'r')
        lines = file.readlines()
        for line in lines:
            match = re.search("<project ?.* name=\"([\.\ a-zA-Z1-9]+)\"", line)
            if match:
                return match.group(1)

    def findActivity(self, xmlFile):
        if not os.path.isfile(xmlFile):
            return
        file = open(xmlFile, 'r')
        lines = file.readlines()
        for line in lines:
            match = re.search("^\s*android:name=\"([\.a-zA-Z1-9]+)\"", line)
            if match:
                return match.group(1)

    def findPackage(self, xmlFile):
        if not os.path.isfile(xmlFile):
            return
        file = open(xmlFile, 'r')
        lines = file.readlines()
        for line in lines:
            match = re.search("package=\"([\.a-zA-Z1-9]+)\"", line)
            if match:
                return match.group(1)

    def findKeystore(self, properiesFile):
        if not os.path.isfile(properiesFile):
            return
        file = open(properiesFile, 'r')
        lines = file.readlines()
        for line in lines:
            match = re.search("^key.store=(.*)$", line)
            if match:
                return match.group(1)

    def locatePath(self, pattern, root=os.curdir):
        for path, dirs, files in os.walk(os.path.abspath(root)):
            for filename in fnmatch.filter(files, pattern):
                return path

class AndroidBuildOnSave(sublime_plugin.EventListener):
    timestamp = ""
    filepath = ""
    filename = ""

    def on_post_save(self, view):
        #check if android project
        folder = sublime.active_window().folders()[0]
        path = self.locatePath("AndroidManifest.xml", folder)
        if path is not None and os.path.isfile(path + os.path.sep + "AndroidManifest.xml"):
            #let's see if project wants to be autobuilt.
            should_build = sublime.load_settings(settings_file).get('compile_on_save')
            if should_build == 1:
                self.filename = "build.prop"
                self.resetTimeStamp()
                self.setTimestamp()
                sublime.active_window().active_view().set_status('Android', 'Project build started')
                AndroidBuildCommand(sublime.active_window()).runQuiet()
                self.on_build()

    def on_build(self, i=0, dir=1):
        if self.timestamp == self.getTimestamp() and sublime.active_window().active_view().get_status('Android') != "":
            before = i % 8
            after = (7) - before
            if not after:
                dir = -1
            if not before:
                dir = 1
            i += dir
            sublime.active_window().active_view().set_status('Android', 'Building project [%s=%s]' % \
                (' ' * before, ' ' * after))
            sublime.set_timeout(lambda: self.on_build(i, dir), 25)
            return
        else:
            sublime.active_window().active_view().set_status('Android', 'Project build succesfully')
            sublime.set_timeout(lambda: self.on_done(), 5000)

    def on_done(self):
         sublime.active_window().active_view().erase_status('Android')

    def locatePath(self, pattern, root=os.curdir):
        for path, dirs, files in os.walk(os.path.abspath(root)):
            for filename in fnmatch.filter(files, pattern):
                return path

    def setFilePath(self):
        if self.filepath == "":
            folder = sublime.active_window().folders()[0]
            path = self.locatePath(self.filename, folder)
            if path is not None:
                self.filepath = os.path.sep.join([path, self.filename])

    def setTimestamp(self):
        self.setFilePath()
        if self.filepath != "":
            self.timestamp = self.getTimestamp()

    def getTimestamp(self):
        if self.filepath != "":
            return str(os.path.getmtime(self.filepath))
        else:
            self.setFilePath()
            return ""

    def resetTimeStamp(self):
        self.filepath = ""
        self.timestamp = ""

class AndroidExecCommand(ExecCommand):
    def finish(self, proc):
        self.window.run_command("refresh_folder_list")
        sublime.active_window().active_view().erase_status('Android')

        if not self.quiet:
            elapsed = time.time() - proc.start_time
            exit_code = proc.exit_code()
            if exit_code == 0 or exit_code == None:
                self.append_string(proc,
                    ("[Finished in %.1fs]" % (elapsed)))
            else:
                self.append_string(proc, ("[Finished in %.1fs with exit code %d]\n"
                    % (elapsed, exit_code)))
                self.append_string(proc, self.debug_text)

        if proc != self.proc:
            return

        errs = self.output_view.find_all_results()
        if len(errs) == 0:
            sublime.status_message("Build finished")
            sublime.active_window().active_view().set_status('Android', 'Project build succesfully')
        else:
            sublime.status_message(("Build finished with %d errors") % len(errs))
            sublime.active_window().active_view().set_status('Android', 'Project build with errors')
        sublime.set_timeout(lambda: self.on_done(), 4000)

    def on_done(self):
         sublime.active_window().active_view().erase_status('Android')

class AndroidCreateCertificateCommand(sublime_plugin.WindowCommand):
    settings = []
    package = ""
    path = ""
    dname = ""
    password = ""
    CN = OU = O = L = ST = C = ""
    keystore = ""

    def run(self):
        for folder in self.window.folders():
            buildxml = self.locatePath("build.xml", folder)
            if buildxml is not None:
                self.path = buildxml

                self.settings = AndroidSettings(sublime.load_settings(settings_file))
                if not self.settings.is_valid():
                    return

                manifest = self.path + os.path.sep + "AndroidManifest.xml"
                self.package = self.findPackage(manifest)

                self.keystore = self.path + os.path.sep + "%s.keystore" % self.package
                if os.path.isfile(self.keystore):
                    if sublime.ok_cancel_dialog("Certificate (%s.keystore) already exists!\n\n" % self.package +
                        "Do you want to replace it?"):
                        self.passwordPrompt()

                else:
                    self.passwordPrompt()

    def generate(self):
        # Delete existing keystore
        if os.path.isfile(self.keystore):
            os.remove(self.keystore)

        # Generate Certificate
        cmd = ["keytool", "-genkey", "-v",
            "-keystore", "%s.keystore" % self.package,
            "-alias", self.package,
            "-keyalg", "RSA",
            "-keysize", "2048", "-validity", "10000",
            # "-keypass", self.password,
            "-storepass", self.password,
            "-dname", self.dname]

        args = {
            "cmd": cmd,
            "working_dir": self.path,

            "env": {"JAVA_HOME": self.settings.jdk},

            "path": os.environ["PATH"] +
                    os.pathsep + self.settings.jdk
        }
        self.window.run_command("exec", args)

        self.setProperties()

    def setProperties(self):
        #Set local.properties
        propertiesFile = self.path + os.path.sep + "local.properties"
        if not os.path.isfile(propertiesFile):
            return
        properties = ""
        exist = False

        # keystore  = "key.store=%s.keystore\n" % (self.path + os.path.sep + self.package)
        keystore  = "key.store=%s.keystore\n" % self.package
        keystore += "key.alias=%s\n" % self.package
        keystore += "key.store.password=%s\n" % self.password
        keystore += "key.alias.password=%s" % self.password

        file = open(propertiesFile, 'r')
        lines = file.readlines()
        for line in lines:
            match = re.search("^key\.(store|alias)\.?(password)?=.*$", line)
            if match:
                if not exist:
                    exist = True
                    properties += keystore
            else:
                properties += line
        if not exist:
            properties += "\n" + keystore

        os.remove(propertiesFile)
        with open(propertiesFile, 'w') as file:
            file.write(properties)

    def locatePath(self, pattern, root=os.curdir):
        for path, dirs, files in os.walk(os.path.abspath(root)):
            for filename in fnmatch.filter(files, pattern):
                return path

    def findPackage(self, xmlFile):
        if not os.path.isfile(xmlFile):
            return
        file = open(xmlFile, 'r')
        lines = file.readlines()
        for line in lines:
            match = re.search("package=\"([\.a-zA-Z1-9]+)\"", line)
            if match:
                return match.group(1)

    def passwordPrompt(self, text = ""):
        self.window.show_input_panel("Enter keystore password: " + text, "", self.passwordCheck, None, None)

    def passwordCheck(self, password):
        if len(password) < 6:
            self.passwordPrompt("Key password must be at least 6 characters")
        else:
            self.password = password
            self.window.show_input_panel("Re-enter new password: ", "", self.passwordConfirm, None, None)

    def passwordConfirm(self, password):
        if self.password != password:
            self.passwordPrompt("They don't match. Try again")
            self.password = ""
        else:
            self.promptCN()

    def promptCN(self):
        self.window.show_input_panel("What is your first and last name?", "", self.promptOU, None, None)

    def promptOU(self, text):
        self.CN = text
        self.window.show_input_panel("What is the name of your organizational unit?", "", self.promptO, None, None)

    def promptO(self, text):
        self.OU = text
        self.window.show_input_panel("What is the name of your organization?", "", self.promptL, None, None)

    def promptL(self, text):
        self.O = text
        self.window.show_input_panel("What is the name of your City or Locality?", "", self.promptST, None, None)

    def promptST(self, text):
        self.L = text
        self.window.show_input_panel("What is the name of your State or Province?", "", self.promptC, None, None)

    def promptC(self, text):
        self.ST = text
        self.window.show_input_panel("What is the two-letter country code for this unit?", "", self.checkC, None, None)

    def checkC(self, text):
        if re.match('^[a-zA-Z]{2}$', text) or re.match('^[a-zA-Z]{0}$', text):
            self.C = text
            self.confirmDName()
        else:
            self.window.show_input_panel("What is the two-letter country code for this unit?", "", self.checkC, None, None)

    def confirmDName(self):
        if self.CN != "" or self.OU != "" or self.O != "" or self.L != "" or self.ST != "" or self.C != "":
            if sublime.ok_cancel_dialog("Is CN=" + self.CN +
                ", OU=" + self.OU + ", O=" + self.O +
                ", L=" + self.L + ", ST=" + self.ST +
                ", C=" + self.C + " correct?"):
                self.dname = "CN=" + self.CN + ", OU=" + self.OU + ", O=" + \
                    self.O + ", L=" + self.L + ", ST=" + self.ST + ", C=" + self.C
                self.generate()
        else:
            if sublime.ok_cancel_dialog("Distinguished Name fields (CN, OU, ...) can't be empty!"):
                self.promptCN()

class AndroidInstallCommand(sublime_plugin.WindowCommand):
    def run(self):
        for folder in self.window.folders():
            buildxml = self.locatePath("build.xml", folder)
            if buildxml is not None:
                path = buildxml

                settings = AndroidSettings(sublime.load_settings(settings_file))
                if not settings.is_valid():
                    return

                buildxml = path + os.path.sep + "build.xml"
                projectName = self.findProject(buildxml)

                if settings.debug:
                    apk = projectName + "-debug.apk"
                else:
                    # apk = projectName + "-release-unsigned.apk"
                    apk = projectName + "-release.apk"

                apk_path = path + os.path.sep + "bin" + os.path.sep + apk
                if os.path.isfile(apk_path):
                    args = {
                        "cmd": [settings.sdk + adb_bin, "-d", "install", apk_path]
                    }
                    self.window.run_command("exec", args)
                else:
                    sublime.message_dialog( "Install failed because %s was not found!\n\nPlease run build and try again." % apk )

    def locatePath(self, pattern, root=os.curdir):
        for path, dirs, files in os.walk(os.path.abspath(root)):
            for filename in fnmatch.filter(files, pattern):
                return path

    def findProject(self, xmlFile):
        if not os.path.isfile(xmlFile):
            return
        file = open(xmlFile, 'r')
        lines = file.readlines()
        for line in lines:
            match = re.search("<project ?.* name=\"([\.\ a-zA-Z1-9]+)\"", line)
            if match:
                return match.group(1)

class AndroidUninstallCommand(sublime_plugin.WindowCommand):
    def run(self):
        settings = AndroidSettings(sublime.load_settings(settings_file))
        if not settings.is_valid():
            return
        for folder in self.window.folders():
                path = self.locatePath("AndroidManifest.xml", folder)
                if path is not None:
                   manifest = path + os.path.sep + "AndroidManifest.xml"
        if manifest is not None:
            package = self.findPackage(manifest)
            args = {
                "cmd": [settings.sdk + adb_bin, "uninstall", package]
            }
            self.window.run_command("exec", args)

    def locatePath(self, pattern, root=os.curdir):
        for path, dirs, files in os.walk(os.path.abspath(root)):
            for filename in fnmatch.filter(files, pattern):
                return path

    def findPackage(self, xmlFile):
        if not os.path.isfile(xmlFile):
            return
        file = open(xmlFile, 'r')
        lines = file.readlines()
        for line in lines:
            match = re.search("package=\"([\.a-zA-Z1-9]+)\"", line)
            if match:
                return match.group(1)

class AndroidAdbShellCommand(sublime_plugin.WindowCommand):
    settings = []

    def run(self):
        self.settings = AndroidSettings(sublime.load_settings(settings_file))
        if not self.settings.is_valid():
            return
        # Check if Terminal is installed http://wbond.net/sublime_packages/terminal
        if not os.path.exists(os.path.join(sublime.packages_path(), "Terminal")):
            sublime.message_dialog( "Sublime Terminal package is not installed.\n\n" +
                "Use Package Control to install it or download it from:\n" +
                "http://wbond.net/sublime_packages/terminal" )
        else:
            # The following is only tested on ubuntu
            param = ''
            if platform == 'windows': param = ''
            elif platform == 'darwin': param = '-x'
            elif platform == 'linux':
                ps = 'ps -eo comm | grep -E "gnome-session|ksmserver|' + \
                    'xfce4-session" | grep -v grep'
                wm = [x.replace("\n", '') for x in os.popen(ps)]
                if wm:
                    if wm[0] == 'gnome-session': param = '-x'
                    elif wm[0] == 'xfce4-session': param = '-x'
                    elif wm[0] == 'ksmserver': param = '-x'
                else: param = '-e'
            args = {
                "parameters": [param, self.settings.sdk + adb_bin, "shell"]
            }
            self.window.run_command("open_terminal", args)

# Runs ADB Logcat, given a filter in the format tag:priority
# tag = the name of the system component where the message came from
# priority = one of the following characters:
#             V - Verbose
#             D - Debug
#             I - Info
#             W - Warning
#             E - Error
#             F - Fatal
#             S - Silent (nothing is printed)
# Read more at http://developer.android.com/guide/developing/tools/adb.html#outputformat
class AndroidAdbLogcatCommand(sublime_plugin.WindowCommand):
    settings = []

    def run(self):
        self.settings = AndroidSettings(sublime.load_settings(settings_file))
        if not self.settings.is_valid():
            return
        self.window.show_input_panel("Filter (tag:priority)", "System.out:I *:S", self.on_input, None, None)

    def on_input(self, text):
        sdk = self.settings.sdk
        if not self.settings.is_valid():
            return
        args = {
            "cmd": [scriptpath + logcat_script,
            text, sdk + adb_bin]
        }
        self.window.run_command("exec", args)

class AndroidCleanCommand(sublime_plugin.WindowCommand):
    def run(self):
        for folder in self.window.folders():
            buildxml = self.locatePath("build.xml", folder)
            if buildxml is not None:
                settings = AndroidSettings(sublime.load_settings(settings_file))
                path = buildxml
                args = {
                    "cmd": [ant_bin, "clean"],
                    "working_dir": path,

                    "env": {"JAVA_HOME": settings.jdk},

                    "path": os.environ["PATH"] +
                            os.pathsep + settings.ant +
                            os.pathsep + settings.jdk +
                            os.pathsep + settings.sdk + "tools" + os.path.sep +
                            os.pathsep + settings.sdk + "platform-tools" + os.path.sep
                }
                self.window.run_command("android_exec", args)

    def locatePath(self, pattern, root=os.curdir):
        for path, dirs, files in os.walk(os.path.abspath(root)):
            for filename in fnmatch.filter(files, pattern):
                return path

class AndroidRefactorStringCommand(sublime_plugin.WindowCommand):
    text = ""
    tag = ""
    region = None
    edit = None

    def run(self):
        #check if android project
        folder = sublime.active_window().folders()[0]
        path = self.locatePath("AndroidManifest.xml", folder)
        if path is not None and os.path.isfile(path + os.path.sep + "AndroidManifest.xml"):

            view = self.window.active_view()

            sels = view.sel()
            new_sels = []
            for sel in sels:
                begin = sel.a
                end = sel.b
                line_begin = view.full_line(sel.a).a
                line_end = view.full_line(sel.b).b
                while view.substr(begin) != '"' and begin >= line_begin:
                    if begin == line_begin:
                        return
                    begin -= 1
                begin += 1
                while view.substr(end) != '"' and end <= line_end:
                    if end == line_end:
                        return
                    end += 1
                new_sels.append(sublime.Region(begin, end))
            for sel in new_sels:
                self.text = view.substr(sel)
                self.tag = self.slugify(view.substr(sel))
                self.region = sel
                sublime.active_window().show_input_panel("String name:", self.tag, self.on_done, None, None)

    def on_done(self, text):
        self.tag = text
        self.add_to_strings_xml(self.text, self.tag)

    def slugify(self, str):
        str = str.lower()
        return re.sub(r'\W+', '_', str)

    def add_to_strings_xml(self, text, tag):
        for folder in sublime.active_window().folders():
            stringsxml = self.locatePath("strings.xml", folder)
            if stringsxml is not None:
                stringsxml += "/strings.xml"
                file = open(stringsxml, 'r')
                strings_content = file.read()
                file.close()
                file = open(stringsxml, 'w')
                new_block = '<string name="' + tag + '">' + text + '</string>'
                strings_content = strings_content.replace("</resources>", "\t" + new_block + "\n</resources>")
                file.write(strings_content)
                file.close()

                if self.window.active_view():
                    args = {"begin": self.region.begin(), "end": self.region.end(), "tag": self.tag}
                    self.window.active_view().run_command("android_replace_with_tag", args )

    def locatePath(self, pattern, root=os.curdir):
        for path, dirs, files in os.walk(os.path.abspath(root)):
            for filename in fnmatch.filter(files, pattern):
                return path

class AndroidReplaceWithTagCommand(sublime_plugin.TextCommand):
    def run(self, edit, begin, end, tag):
        self.view.replace(edit, sublime.Region(begin, end), "@string/" + tag)

class AndroidInsertSnippetCommand(sublime_plugin.TextCommand):
    snippets = []
    snippetsHeaders = []

    def run(self, text):
        self.snippets = self.getSnippets()
        self.snippetsHeaders = self.stripFileExt(self.snippets)
        self.view.window().show_quick_panel(self.snippetsHeaders, self.on_done, sublime.MONOSPACE_FONT)
        return

    def getSnippets(self):
        snippet_path = os.path.sep.join([os.path.dirname(os.path.abspath(__file__)), "snippets/"])
        snippets = os.listdir(snippet_path)
        snippets.sort()
        return snippets

    def stripFileExt(self, files):
        filenames = []
        for filename in files:
            filenames.append(os.path.splitext(filename)[0])
        return filenames

    def on_done(self, index):
        if index < 0:
            return
        snippet = self.snippets[index]
        self.view.run_command('insert_snippet', {"name": "Packages/Android/snippets/" + snippet})

class AndroidExploreSnippets(sublime_plugin.WindowCommand):
    def run(self):
        self.window.run_command('open_dir', {"dir": "$packages/Android/snippets/"})
        return

readme = """\
Android projects are the projects that eventually get built into an .apk file
that you install onto a device. They contain things such as application
source code and resource files.

Some are generated for you by default, while others should be created if
required. The following directories and files comprise an Android project:

src/
    Contains your stub Activity file, which is stored at
    src/your/package/namespace/ActivityName.java All other source code files
    (such as .java or .aidl files) go here as well.
bin/
    Output directory of the build. This is where you can find the final .apk
    file and other compiled resources.
jni/
    Contains native code sources developed using the Android NDK. For more
    information, see the Android NDK documentation.
gen/
    Contains the Java files generated by ADT, such as your R.java file and
    interfaces created from AIDL files.
assets/
    This is empty. You can use it to store raw asset files. Files that you
    save here are compiled into an .apk file as-is, and the original filename
    is preserved. You can navigate this directory in the same way as a
    typical file system using URIs and read files as a stream of bytes using
    the the AssetManager. For example, this is a good location for textures
    and game data.
res/
    Contains application resources, such as drawable files, layout files,
    and string values. See Application Resources for more information.
res/anim/
    For XML files that are compiled into animation objects. See the Animation
    resource type.
res/color/
    For XML files that describe colors. See the Color Values resource type.
res/drawable/
    For bitmap files (PNG, JPEG, or GIF), 9-Patch image files, and XML files
    that describe Drawable shapes or a Drawable objects that contain multiple
    states (normal, pressed, or focused). See the Drawable resource type.
res/layout/
    XML files that are compiled into screen layouts (or part of a screen).
    See the Layout resource type.
res/menu/
    For XML files that define application menus. See the Menus resource type.
res/raw/
    For arbitrary raw asset files. Saving asset files here instead of in
    the assets/ directory only differs in the way that you access them. These
    files are processed by aapt and must be referenced from the application
    using a resource identifier in the R class. For example, this is a good
    place for media, such as MP3 or Ogg files.
res/values/
    For XML files that are compiled into many kinds of resource. Unlike other
    resources in the res/ directory, resources written to XML files in this
    folder are not referenced by the file name. Instead, the XML element type
    controls how the resources is defined within them are placed into
    the R class.
res/xml/
    For miscellaneous XML files that configure application components.
    For example, an XML file that defines a androidcreen,
    AppWidgetProviderInfo, or Searchability Metadata. See Application
    Resources for more information about configuring these application
    components.
libs/
    Contains private libraries.
AndroidManifest.xml
    The control file that describes the nature of the application and each
    of its components. For instance, it describes:
    - certain qualities about the activities, services, intent receivers,
      and content providers
    - what permissions are requested; what external libraries are needed
    - what device features are required, what API Levels are supported
      or required
    See the AndroidManifest.xml documentation for more information
project.properties
    This file contains project settings, such as the build target. This file
    is integral to the project, so maintain it in a source revision control
    system. To edit project properties in Eclipse, right-click the project
    folder and select Properties.
local.properties
    Customizable computer-specific properties for the build system. If you
    use Ant to build the project, this contains the path to the SDK
    installation. Because the content of the file is specific to the
    local installation of the SDK, the local.properties should not be
    maintained in a source revision control system. If you use Eclipse,
    this file is not used.
ant.properties
    Customizable properties for the build system. You can edit this file to
    override default build settings used by Ant and also provide the location
    of your keystore and key alias so that the build tools can sign your
    application when building in release mode. This file is integral to
    the project, so maintain it in a source revision control system.
    If you use Eclipse, this file is not used.
build.xml
    The Ant build file for your project. This is only applicable for projects that you build with Ant."""