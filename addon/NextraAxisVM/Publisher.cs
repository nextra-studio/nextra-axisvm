using System;
using System.IO;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

namespace NextraAxisVM
{
    /// <summary>
    /// Makes this AxisVM reachable for out-of-process COM clients (the NextraAxisVM Python worker).
    ///
    /// AxisVM started by the user is not in the Running Object Table, so GetActiveObject fails and PyAxisVM could
    /// only start a new, empty AxisVM. From inside the running AxisVM this registers the item moniker
    /// !NextraAxisVM.Host.&lt;pid&gt; for the Host helper object (one per instance, never ambiguous);
    /// Host.GetApplication() hands out the IAxisVMApplication.
    ///
    /// The AxisVM application object itself is deliberately NOT put in the ROT: AxisVM disconnects it when its last
    /// COM client goes away (a weak entry dies with it), and a strong entry would count as a connected client and
    /// change how AxisVM closes. The host is a plain .NET object and is registered STRONG: a weak (table-weak) entry is
    /// torn down by COM as soon as the first client releases its last reference to the host, so the second connection
    /// would get MK_E_UNAVAILABLE. Holding the host does not keep AxisVM open; Revoke() runs in Addon_Deinit.
    /// Also writes %APPDATA%\NextraAxisVM\instances\axisvm-&lt;pid&gt;.json so clients can list instances cheaply.
    /// </summary>
    internal static class Publisher
    {
        const int ROTFLAGS_REGISTRATIONKEEPSALIVE = 1;   // strong entry for the host object only (see class comment)

        [DllImport("ole32.dll")] static extern int GetRunningObjectTable(int reserved, out IRunningObjectTable prot);
        [DllImport("ole32.dll")] static extern int CreateItemMoniker([MarshalAs(UnmanagedType.LPWStr)] string delim, [MarshalAs(UnmanagedType.LPWStr)] string item, out IMoniker ppmk);

        static int hostCookie;
        internal static Host HostObject;
        internal static string LastError = "";

        internal static int Pid { get { return Process.GetCurrentProcess().Id; } }
        internal static string AppDir { get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "NextraAxisVM"); } }
        static string InstanceFile { get { return Path.Combine(AppDir, "instances", "axisvm-" + Pid + ".json"); } }
        internal static bool Published { get { return hostCookie != 0; } }

        /// <summary>Registers (or re-registers) this AxisVM. Safe to call repeatedly; never throws.</summary>
        internal static bool Publish(object iAxisVMApp)
        {
            try
            {
                if (iAxisVMApp == null) { LastError = "AxisVM passed no application object"; return false; }
                Revoke();
                HostObject = HostObject ?? new Host();
                HostObject.App = iAxisVMApp;

                IRunningObjectTable rot;
                Marshal.ThrowExceptionForHR(GetRunningObjectTable(0, out rot));
                IMoniker mk;
                Marshal.ThrowExceptionForHR(CreateItemMoniker("!", "NextraAxisVM.Host." + Pid, out mk));
                hostCookie = rot.Register(ROTFLAGS_REGISTRATIONKEEPSALIVE, HostObject, mk);

                WriteInstanceFile();
                LastError = "";
                Log("published pid " + Pid);
                return true;
            }
            catch (Exception ex)
            {
                LastError = ex.Message;
                Log("publish failed: " + ex);
                return false;
            }
        }

        internal static void Revoke()
        {
            try
            {
                IRunningObjectTable rot;
                if (hostCookie != 0 && GetRunningObjectTable(0, out rot) == 0) try { rot.Revoke(hostCookie); } catch { }
            }
            catch { }
            hostCookie = 0;
            try { if (File.Exists(InstanceFile)) File.Delete(InstanceFile); } catch { }
        }

        static void WriteInstanceFile()
        {
            Directory.CreateDirectory(Path.GetDirectoryName(InstanceFile));
            string exe = "";
            try { exe = Process.GetCurrentProcess().MainModule.FileName; } catch { }
            string json = "{\"pid\": " + Pid
                + ", \"started\": \"" + DateTime.Now.ToString("yyyy-MM-ddTHH:mm:ss") + "\""
                + ", \"addon\": \"" + Host.AddonVersion + "\""
                + ", \"exe\": " + Json.Str(exe)
                + ", \"host_moniker\": \"NextraAxisVM.Host." + Pid + "\"}";
            File.WriteAllText(InstanceFile, json);
        }

        internal static void Log(string line)
        {
            try
            {
                Directory.CreateDirectory(AppDir);
                string p = Path.Combine(AppDir, "addon.log");
                if (File.Exists(p) && new FileInfo(p).Length > 512 * 1024) File.Delete(p);
                File.AppendAllText(p, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " [" + Pid + "] " + line + Environment.NewLine);
            }
            catch { }
        }
    }
}
