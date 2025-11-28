from tkinter import *
from tkinter import filedialog
from tkinter import scrolledtext
from tkinter import ttk
from tkinter import messagebox
import subprocess
import json
import queue
import threading
import time
import argparse


def DAP_Read(pipe, queue):
    while(True):
        line = pipe.readline()
        queue.put(pipe.read(int(line.split(" ")[-1].strip()) + 1 ))

class DebugBackend:
    def __init__(self, locals_handler, select_running_line, stack_trace):
        self.use_lldb = False
        possible_command_lines = [["gdb", "-i=dap"], ["xcrun", "lldb-dap"], ["lldb-dap"], ["lldb-dap-20"]]
        self.debugger = None
        for command in possible_command_lines:
            print(f"Trying to run {' '.join(command)}")
            try:
                self.debugger = subprocess.Popen(command, stdin = subprocess.PIPE, stdout = subprocess.PIPE, universal_newlines = True)
            except FileNotFoundError:
                print("Unsuccessful, trying next command line...")
                self.use_lldb = True
                continue
            break    
        if not self.debugger:
            print("No debugger found, exiting")
            exit()
        self.stdout = queue.Queue()
        self.reader = threading.Thread(target=DAP_Read, args=(self.debugger.stdout, self.stdout), daemon=True)
        self.reader.start()
        self.sequence = 1
        self.initialized = False
        self.executable = None
        self.locals_handler = locals_handler
        self.running_line = select_running_line
        self.stacktrace = stack_trace
        self.tid = 0
        self.current_variables = []
        self.bp_sources = []
        time.sleep(1)
        self.send_dap({"type": "request", "command":"initialize", "arguments":{"adapterID": "debugger"}})
    
    def set_breakpoint(self, filename, lineno):
        if not lineno:
            for f in self.bp_sources:
                self.send_dap({"type": "request", "command":"setBreakpoints","arguments":{"source":{"path":f}}})
            self.bp_sources = []
            return
        self.bp_sources.append(filename)
        self.send_dap({"type": "request", "command":"setBreakpoints","arguments":{"source":{"path":filename}, "breakpoints":[{"line":lineno}]}})

    def cont(self):
        self.send_dap({"type": "request", "command":"continue", "arguments": {"threadId":self.tid}})

    def send_dap(self, args):
        combined = json.dumps({"seq": self.sequence} | args)
        print(f"SENDING: {combined}")
        self.sequence += 1
        header = f"Content-Length: {len(combined)}\r\n\r\n"
        full_data = "".join([header, combined])
        self.debugger.stdin.write(full_data)
        self.debugger.stdin.flush()

    def handle_event(self, event):
        print(event)
        if("event" in event and event["event"] == "stopped"):
            if(event["body"]["reason"] in ["breakpoint", "step", "signal"]):
                self.tid = event["body"]["threadId"]
                self.send_dap({"type":"request", "command":"stackTrace", "arguments":{"threadId":self.tid}})
        
        if("type" in event and event["type"] == "response" and event["command"] == "stackTrace" and event["success"]):
            self.stacktrace(event["body"]["stackFrames"])
            self.send_dap({"type": "request", "command":"scopes", "arguments":{"frameId":event["body"]["stackFrames"][0]["id"]}})
            self.running_line(event["body"]["stackFrames"][0]["source"]["path"], event["body"]["stackFrames"][0]["line"])

        if("type" in event and event["type"] == "response" and event["command"] == "scopes" and event["success"]):
            l = [x for x in event["body"]["scopes"] if x["name"] in ["Locals", "Arguments"]]
            self.current_variables = []
            for ref in l:
                self.send_dap({"type": "request", "command":"variables", "arguments":{"variablesReference": ref["variablesReference"]}})

        if("type" in event and event["type"] == "response" and event["command"] == "variables" and event["success"]):
            response_to = event["request_seq"]
            for x in event["body"]["variables"]:
                self.current_variables.append((x["name"], x["value"], x["variablesReference"], response_to, self.sequence))
                self.send_dap({"type": "request", "command": "variables", "arguments":{"variablesReference":x["variablesReference"]}})
            self.locals_handler(self.current_variables)

        if("command" in event and event["command"] == "initialize"):
            self.initialized = True
            if self.executable:
                self.send_dap({"type": "request", "command":"launch", "arguments":{"nodebug": "false", "program": self.executable}})
                self.executable = None
            
            

    def step(self):
        self.send_dap({"type": "request", "command":"next", "arguments":{"threadId": self.tid}} )

    def get_dap_messages(self):
        while(True):
            try:
                text = self.stdout.get_nowait()
                parsed = json.loads(text)
                self.handle_event(parsed)
            except queue.Empty as e:
                break

    def select_program(self, executable):
        if self.initialized:
            self.send_dap({"type": "request", "command":"launch", "arguments":{"nodebug": "false", "program": executable}})
        else:
            self.executable = executable
            
    def run_program(self):
        self.send_dap({"type": "request", "command":"configurationDone"})
        

class DebugFrontend:
    def __init__(self):
        ap = argparse.ArgumentParser()
        ap.add_argument("-e", help="Set executable to debug")
        ap.add_argument("-s", help="Default source to show")
        self.opts = ap.parse_args()

        self.backend = DebugBackend(self.update_locals, self.select_running_line, self.stack_trace)
        self.breakpoint = None
        self.executable = None
        self.source = None

        self.root = Tk()
        self.root.title("Simple debugger")
        self.root.columnconfigure(0, weight = 1)
        self.root.rowconfigure(0, weight = 1)
        frame = ttk.Frame(self.root, padding = 10)
        frame.grid(sticky="nswe")
        frame.columnconfigure(0, weight = 1)
        frame.rowconfigure(0, weight = 1)

        source_frame = ttk.Frame(self.root, padding = 10, width = 500, height = 1000)
        source_frame.grid(row = 0, column = 0, sticky = "nswe")
        source_frame.columnconfigure(0, weight = 1)
        source_frame.rowconfigure(0, weight = 1)
        other_frame = ttk.Frame(self.root, padding = 10)
        other_frame.grid(row = 0, column = 1, sticky = "nswe")
        button_frame = ttk.Frame(other_frame, padding = 10)
        button_frame.grid(row = 0, column = 0, sticky = "nw")
        locals_frame = ttk.Frame(other_frame, padding = 10)
        locals_frame.grid(row = 2, column = 0)
        trace_frame = ttk.Frame(other_frame, padding = 10)
        trace_frame.grid(row = 3, column = 0)

        self.status = ttk.Label(button_frame, text = "Status: NOT RUNNING")
        self.status.grid(row = 0, column = 0, columnspan=2, sticky = "nw")
        
        ttk.Button(button_frame, text = "Load EXE", command = self.load_exe).grid(row = 1, column = 0, sticky = "nw")
        ttk.Button(button_frame, text = "Load Source", command = self.load_source).grid(row = 2, column = 0, sticky = "nw")
        ttk.Button(button_frame, text = "Set breakpoint", command = self.bp).grid(row = 3, column = 0, sticky = "nw")
        ttk.Button(button_frame, text = "Run", command = self.run).grid(row = 4, column = 0, sticky = "nw")
        ttk.Button(button_frame, text = "Step", command = self.step).grid(row = 5, column = 0, sticky = "nw")
        ttk.Button(button_frame, text = "Continue", command = self.cont).grid(row = 1, column = 1, sticky = "nw")
        ttk.Button(button_frame, text = "Remove breakpoints", command = self.bp_remove).grid(row = 2, column = 1, sticky = "nw")
        
        self.source_window = ttk.Treeview(source_frame, height = 50, selectmode = "browse")
        self.source_window.columnconfigure(0, weight=1)
        self.source_window.grid(row = 0, column = 0, sticky="nswe")
        self.locals = ttk.Treeview(locals_frame, selectmode = "browse", columns=["obj_ref", "sub_request"], displaycolumns=[])
        self.locals.grid(row = 0, column = 0)
        self.trace = ttk.Treeview(trace_frame, selectmode = "browse", columns=["path", "line"], displaycolumns=[])
        self.trace.grid(row = 0, column = 0)
        self.trace.bind("<<TreeviewSelect>>", self.select_bt_source)
        self.root.after(100, self.pump_messages)

        if(self.opts.e):
            self.executable = self.opts.e
            self.backend.select_program(self.executable)
        if(self.opts.s):
            self.source = self.opts.s
            self.show_source()

        self.img_line = PhotoImage(name="select", file="icons/current_line.png")
        self.img_bp = PhotoImage(name="bp", file="icons/breakpoint.png")

        self.root.mainloop()

    def set_status(self, text):
        self.status["text"] = f"Status: {text}"

    def select_bt_source(self, event):
        self.source, lineno = event.widget.item(event.widget.focus(), option="values")
        self.show_source()
        self.select_running_line(self.source, int(lineno))

    def stack_trace(self, frames):
        for item in self.trace.get_children():
            self.trace.delete(item)
        for frame in frames:
            file = frame["source"]["path"]
            name = frame["source"]["name"]
            line = frame["line"]
            self.trace.insert("", "end", text = f"{name}:{line}", values=[file, line])

    def update_locals(self, values):
        self.set_status("Stopped")
        for item in self.locals.get_children():
            self.locals.delete(item)
        resources = {}
        for pair in values:
            print(pair)
            resources[pair[-1]] = self.locals.insert("","end", text = f"{pair[0]}: {pair[1]}", values = [pair[2]])
            if(pair[-2] in resources):
                self.locals.move(resources[pair[-1]], resources[pair[-2]], 0)
            
            

    def select_running_line(self, path, lineno):
        self.set_status("Stopped")
        if(self.source != path):
            self.source = path
            self.show_source(silent_fail = True)
        gui_line = lineno - 1
        all_lines = self.source_window.get_children()
        for line in all_lines:
            self.source_window.item(line, image="")
        self.show_bp()
        if(gui_line > len(all_lines)):
            return
        target_line = self.source_window.get_children()[gui_line]
        self.source_window.item(target_line, option=None, image="select")

    def step(self):
        self.backend.step()

    def bp_remove(self):
        self.breakpoint = None
        self.backend.set_breakpoint(self.source, None)

    def cont(self):
        self.set_status("Running")
        self.backend.cont()

    def pump_messages(self):
        self.backend.get_dap_messages()
        self.root.after(10, self.pump_messages)

    def bp(self):
        lineno = self.source_window.index(self.source_window.focus())
        self.breakpoint = (self.source, lineno)
        self.backend.set_breakpoint(self.source, self.breakpoint[1] + 1)
        self.show_bp()

    def show_bp(self):
        if(self.breakpoint and self.breakpoint[0] == self.source):
            self.source_window.item(self.source_window.get_children()[self.breakpoint[1]], image="bp")

    def run(self):
        if self.executable == None:
            messagebox.Message(message=f"You must select an executable to run").show()
            return
        self.set_status("Running")
        self.backend.run_program()

    def load_exe(self):
        try:
            self.executable = filedialog.askopenfilename()
            self.backend.select_program(self.executable)
            self.set_status("Ready")
        except:
            return

    def load_source(self):
        self.source = filedialog.askopenfilename()
        self.show_source()

    def show_source(self, silent_fail=False):
        for item in self.source_window.get_children():
            self.source_window.delete(item)
        try:
            with open(self.source) as f:
                for line in f:
                    self.source_window.insert("", "end", text = line)
        except FileNotFoundError:
            if not silent_fail:
                messagebox.Message(message=f"File {self.source} not found!").show()

if __name__ == "__main__":
    DebugFrontend()
