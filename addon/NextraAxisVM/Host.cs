using System;
using System.Runtime.InteropServices;

namespace NextraAxisVM
{
    /// <summary>
    /// Late-bound (IDispatch) helper published next to the AxisVM application. Calls from the Python worker are
    /// marshalled onto AxisVM's main thread, so the code here talks to AxisVM in-process (fast, no cross-process
    /// round trip per property). All methods take and return JSON strings and never throw across COM.
    /// </summary>
    [ComVisible(true)]
    [ClassInterface(ClassInterfaceType.AutoDispatch)]
    public class Host
    {
        public const string AddonVersion = "0.1.0";
        internal object App;

        public string Version() { return AddonVersion; }

        public int ProcessId() { return Publisher.Pid; }

        /// <summary>The running IAxisVMApplication, marshalled to the caller's process as a normal COM reference.</summary>
        [return: MarshalAs(UnmanagedType.IUnknown)]
        public object GetApplication() { return App; }

        /// <summary>Round trip check: returns {"ok":true,...} with the current model file name.</summary>
        public string Ping()
        {
            try
            {
                var a = (AxisVM.IAxisVMApplication)App;
                string file = "";
                try { file = a.Models.Item[1].FileName; } catch { }
                return "{\"ok\": true, \"addon\": \"" + AddonVersion + "\", \"pid\": " + Publisher.Pid + ", \"file\": " + Json.Str(file) + "}";
            }
            catch (Exception ex) { return Json.Error(ex); }
        }

        /// <summary>Builds the model from a Rhino AxisBridge export (schema 2 JSON). options: JSON
        /// {"length":"m|mm|cm","force":"kN|N","tol_mm":1,"dry_run":false,"auto_intersect":true}. Returns a JSON report.</summary>
        public string RhinoImport(string jsonPath, string optionsJson)
        {
            try { return RhinoImportRunner.Run(App, jsonPath, optionsJson); }
            catch (Exception ex) { return Json.Error(ex); }
        }
    }

    internal static class Json
    {
        internal static string Str(string s)
        {
            if (s == null) return "null";
            var sb = new System.Text.StringBuilder("\"");
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4")); else sb.Append(c);
                        break;
                }
            }
            return sb.Append('"').ToString();
        }

        internal static string Error(Exception ex)
        {
            var e = ex is System.Reflection.TargetInvocationException && ex.InnerException != null ? ex.InnerException : ex;
            return "{\"ok\": false, \"error\": " + Str(e.GetType().Name + ": " + e.Message) + "}";
        }
    }
}
