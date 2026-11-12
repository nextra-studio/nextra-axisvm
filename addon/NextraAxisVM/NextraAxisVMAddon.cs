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
                // 16x16: the red Nextra "N" (icon16.png, embedded). AxisVM wants a BMP with a colour key (magenta) and no
                // alpha: transparent pixels become magenta, half-transparent edges are blended onto the toolbar grey so
                // they do not show a pink fringe.
                using (var bmp = new Bitmap(16, 16, System.Drawing.Imaging.PixelFormat.Format24bppRgb))
                {
                    using (var g = Graphics.FromImage(bmp)) g.Clear(Color.Magenta);
                    using (var s = typeof(NextraAxisVMAddon).Assembly.GetManifestResourceStream("NextraAxisVM.icon16.png"))
                    {
                        if (s != null)
                            using (var src = new Bitmap(s))
                            {
                                var bg = SystemColors.Control;
                                for (int y = 0; y < 16 && y < src.Height; y++)
                                    for (int x = 0; x < 16 && x < src.Width; x++)
                                    {
                                        var c = src.GetPixel(x, y);
                                        if (c.A < 64) continue;
                                        int a = c.A;
                                        bmp.SetPixel(x, y, Color.FromArgb((c.R * a + bg.R * (255 - a)) / 255,
                                                                          (c.G * a + bg.G * (255 - a)) / 255,
                                                                          (c.B * a + bg.B * (255 - a)) / 255));
                                    }
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
            using (var dialog = new StatusForm(msg, ok)) dialog.ShowDialog();
            return 1;
        }
    }
}
