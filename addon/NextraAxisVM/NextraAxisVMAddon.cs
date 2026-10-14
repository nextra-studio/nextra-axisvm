using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;
using AxisVMDotNetAddonPluginInterface_v1_0;

namespace NextraAxisVM
{
    /// <summary>
    /// AxisVM add-on entry. AxisVM calls Plugin_Init / Addon_Init when it loads the DLL at start-up: that is where the
    /// running AxisVM is published for the AI tools, so nothing has to be clicked. The menu / toolbar item
    /// "Nextra AI" shows the connection state and re-publishes on demand.
    /// </summary>
    public class NextraAxisVMAddon : IAxisVMDotNetAddonPluginInterface_v1_0
    {
        public int Version { get { return 1; } }
        public int SubVersion { get { return 0; } }
        public int AxisVMMainFormHandle { get; set; }
        public int AxisVMApplicationHandle { get; set; }

        // ---- menu (plugin) ----
        public string Plugin_MenuItemText { get { return "Nextra AI"; } }
        public string Plugin_GetTranslatedMenuItemText(int PrgLang) { return "Nextra AI"; }
        public int Plugin_IsMenuItemEnabled(object iAxisVMApp) { return 1; }
        public int Plugin_IsMenuItemVisible(object iAxisVMApp) { return 1; }
        public int Plugin_IsModalWindow { get { return 0; } }
        public void Plugin_Init(object iAxisVMApp) { Init(iAxisVMApp, "Plugin_Init"); }
        public void Plugin_Deinit(object iAxisVMApp) { Deinit("Plugin_Deinit"); }
        public int Plugin_Execute(object iAxisVMApp) { return ShowStatus(iAxisVMApp); }

        // ---- toolbar (addon) ----
        public string Addon_HintText { get { return "Nextra AI: connect this AxisVM to the AI tools"; } }
        public string Addon_GetTranslatedHintText(int PrgLang) { return Addon_HintText; }
        public int Addon_IsItemEnabled(object iAxisVMApp) { return 1; }
        public int Addon_IsItemVisible(object iAxisVMApp) { return 1; }
        public int Addon_IsModalWindow { get { return 0; } }
        public int Addon_ButtonPlaceFormId { get { return 0; } }
        public int Addon_ButtonPlaceToolbarId { get { return 1; } }
        public int Addon_FormHandle { get; set; }
        public void Addon_Init(object iAxisVMApp) { Init(iAxisVMApp, "Addon_Init"); }
        public void Addon_Deinit(object iAxisVMApp) { Deinit("Addon_Deinit"); }
        public int Addon_Execute(object iAxisVMApp) { return ShowStatus(iAxisVMApp); }

        public int Addon_IconBitmapTransparentColor { get { return ColorTranslator.ToWin32(Color.Magenta); } }
        public byte[] Addon_IconBitmap
        {
            get
            {
                // 16x16: a green "N" on a dark tile (same accent as NextraRhinoGh).
                using (var bmp = new Bitmap(16, 16))
                {
                    using (var g = Graphics.FromImage(bmp))
                    {
                        g.Clear(Color.Magenta);
                        using (var b = new SolidBrush(Color.FromArgb(26, 127, 55))) g.FillRectangle(b, 1, 1, 14, 14);
                        using (var p = new Pen(Color.White, 2))
                        {
                            g.DrawLine(p, 5, 12, 5, 4);
                            g.DrawLine(p, 5, 4, 11, 12);
                            g.DrawLine(p, 11, 12, 11, 4);
                        }
                    }
                    using (var ms = new MemoryStream())
                    {
                        bmp.Save(ms, System.Drawing.Imaging.ImageFormat.Bmp);
                        return ms.ToArray();
                    }
                }
            }
        }

        // ---- shared ----
        static int initCount;

        static void Init(object app, string from)
        {
            // AxisVM may call both Plugin_Init and Addon_Init; publishing twice is harmless but once is enough.
            try
            {
                if (initCount++ > 0 && Publisher.Published) return;
                Publisher.Log(from);
                Publisher.Publish(app);
            }
            catch (Exception ex) { Publisher.Log(from + " failed: " + ex.Message); }
        }

        static void Deinit(string from)
        {
            try { Publisher.Log(from); Publisher.Revoke(); } catch { }
        }

        static int ShowStatus(object app)
        {
            bool ok = Publisher.Publish(app);   // clicking always (re)connects
            string msg = ok
                ? "This AxisVM is connected to the Nextra AI tools.\r\n\r\n"
                  + "Process id: " + Publisher.Pid + "\r\nAdd-on: " + Host.AddonVersion + "\r\n\r\n"
                  + "Ask your AI app (Claude / ChatGPT) to work on the open model. "
                  + "With several AxisVM windows open, tell it which file to use."
                : "Could not connect this AxisVM to the AI tools:\r\n\r\n" + Publisher.LastError
                  + "\r\n\r\nLog: " + Path.Combine(Publisher.AppDir, "addon.log");
            MessageBox.Show(msg, "Nextra AI", MessageBoxButtons.OK, ok ? MessageBoxIcon.Information : MessageBoxIcon.Warning);
            return 1;
        }
    }
}
