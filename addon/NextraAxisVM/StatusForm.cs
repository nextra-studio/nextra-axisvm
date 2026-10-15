using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace NextraAxisVM
{
    /// <summary>Presentation only; publishing and the status message stay in the add-on entry point.</summary>
    internal sealed class StatusForm : Form
    {
        static readonly Color Background = Color.FromArgb(246, 248, 251);
        static readonly Color Accent = Color.FromArgb(0, 102, 180);
        static readonly Color Orange = Color.FromArgb(230, 126, 34);
        readonly Font headingFont = new Font("Segoe UI", 12F, FontStyle.Bold);
        readonly Font bodyFont = new Font("Segoe UI", 9F);

        internal StatusForm(string message, bool connected)
        {
            Text = "Nextra AI";
            Font = bodyFont;
            AutoScaleDimensions = new SizeF(96F, 96F);
            AutoScaleMode = AutoScaleMode.Dpi;
            BackColor = Background;
            ForeColor = Color.FromArgb(36, 53, 72);
            ClientSize = new Size(520, 350);
            FormBorderStyle = FormBorderStyle.FixedDialog;
            StartPosition = FormStartPosition.CenterParent;
            MaximizeBox = false;
            MinimizeBox = false;
            ShowInTaskbar = false;

            var header = new Panel { Dock = DockStyle.Top, Height = 88, Padding = new Padding(16, 10, 16, 10), BackColor = Accent };
            header.Controls.Add(new Label
            {
                Text = connected ? "Connected to the AI tools" : "Could not connect to the AI tools",
                Dock = DockStyle.Fill, Padding = new Padding(0, 5, 0, 0),
                ForeColor = Color.White, BackColor = Color.Transparent, UseMnemonic = false
            });
            header.Controls.Add(new Label
            {
                Text = "Nextra AI", Dock = DockStyle.Top, Height = 25, Font = headingFont,
                ForeColor = Color.White, BackColor = Color.Transparent
            });
            header.Paint += delegate(object sender, PaintEventArgs e)
            {
                using (var fill = new LinearGradientBrush(header.ClientRectangle,
                    Color.FromArgb(13, 121, 199), Color.FromArgb(0, 86, 156), LinearGradientMode.Vertical))
                    e.Graphics.FillRectangle(fill, header.ClientRectangle);
                using (var highlight = new Pen(Color.FromArgb(45, Color.White)))
                    e.Graphics.DrawLine(highlight, 0, 0, header.Width, 0);
                using (var stripe = new SolidBrush(Orange))
                    e.Graphics.FillRectangle(stripe, 0, header.Height - 3, header.Width, 3);
            };

            var body = new Panel { Dock = DockStyle.Fill, Padding = new Padding(16), BackColor = Background };
            var card = new StatusCard { Dock = DockStyle.Fill, Padding = new Padding(16) };
            var scroll = new Panel { Dock = DockStyle.Fill, AutoScroll = true, BackColor = Color.White };
            var content = new Label
            {
                Text = message, AutoSize = true, UseMnemonic = false,
                BackColor = Color.White, Location = Point.Empty, TabIndex = 0
            };
            scroll.Controls.Add(content);
            EventHandler wrapContent = delegate
            {
                var maximum = new Size(Math.Max(40,
                    scroll.ClientSize.Width - SystemInformation.VerticalScrollBarWidth - 4), 0);
                if (content.MaximumSize != maximum) content.MaximumSize = maximum;
            };
            scroll.Resize += wrapContent;
            content.SizeChanged += wrapContent;
            card.Controls.Add(scroll);
            body.Controls.Add(card);

            var footer = new FlowLayoutPanel
            {
                Dock = DockStyle.Bottom, Height = 56, Padding = new Padding(12, 10, 12, 10),
                BackColor = Color.White, FlowDirection = FlowDirection.RightToLeft
            };
            var close = new RoundedButton
            {
                Text = "OK", DialogResult = DialogResult.OK, Size = new Size(92, 34), Margin = Padding.Empty
            };
            footer.Controls.Add(close);
            Controls.Add(body);
            Controls.Add(footer);
            Controls.Add(header);
            AcceptButton = close;
            CancelButton = close;
            Shown += delegate
            {
                Rectangle available = Screen.FromControl(this).WorkingArea;
                Size = new Size(Math.Min(Width, available.Width - 40), Math.Min(Height, available.Height - 60));
            };
        }

        protected override void Dispose(bool disposing)
        {
            base.Dispose(disposing);
            if (disposing) { headingFont.Dispose(); bodyFont.Dispose(); }
        }

        static GraphicsPath Rounded(Rectangle bounds, int radius)
        {
            var path = new GraphicsPath();
            int d = Math.Min(radius * 2, Math.Min(bounds.Width, bounds.Height));
            path.AddArc(bounds.Left, bounds.Top, d, d, 180, 90);
            path.AddArc(bounds.Right - d, bounds.Top, d, d, 270, 90);
            path.AddArc(bounds.Right - d, bounds.Bottom - d, d, d, 0, 90);
            path.AddArc(bounds.Left, bounds.Bottom - d, d, d, 90, 90);
            path.CloseFigure();
            return path;
        }

        sealed class StatusCard : Panel
        {
            internal StatusCard() { DoubleBuffered = true; BackColor = Background; }

            protected override void OnPaint(PaintEventArgs e)
            {
                base.OnPaint(e);
                if (Width < 4 || Height < 4) return;
                e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
                using (var path = Rounded(new Rectangle(1, 1, Width - 3, Height - 3), 8))
                using (var fill = new SolidBrush(Color.White))
                using (var border = new Pen(Color.FromArgb(185, 201, 217)))
                {
                    e.Graphics.FillPath(fill, path);
                    e.Graphics.DrawPath(border, path);
                }
            }
        }

        sealed class RoundedButton : Button
        {
            bool hover, pressed;

            internal RoundedButton()
            {
                DoubleBuffered = true;
                FlatStyle = FlatStyle.Flat;
                FlatAppearance.BorderSize = 0;
                BackColor = Accent;
                ForeColor = Color.White;
                UseVisualStyleBackColor = false;
                Cursor = Cursors.Hand;
                MouseEnter += delegate { hover = true; Invalidate(); };
                MouseLeave += delegate { hover = false; pressed = false; Invalidate(); };
                MouseDown += delegate { pressed = true; Invalidate(); };
                MouseUp += delegate { pressed = false; Invalidate(); };
                GotFocus += delegate { Invalidate(); };
                LostFocus += delegate { Invalidate(); };
            }

            protected override void OnPaint(PaintEventArgs e)
            {
                if (Width < 4 || Height < 4) return;
                e.Graphics.Clear(Parent == null ? Color.White : Parent.BackColor);
                e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
                var bounds = new Rectangle(1, 1, Width - 3, Height - 3);
                Color bottom = Color.FromArgb(0, 96, 170);
                Color top = pressed ? bottom : hover ? Color.FromArgb(30, 142, 218) : Color.FromArgb(18, 126, 204);
                using (var path = Rounded(bounds, 6))
                using (var fill = new LinearGradientBrush(bounds, top, bottom, LinearGradientMode.Vertical))
                using (var border = new Pen(Color.FromArgb(0, 85, 153)))
                {
                    e.Graphics.FillPath(fill, path);
                    e.Graphics.DrawPath(border, path);
                }
                TextRenderer.DrawText(e.Graphics, Text, Font, ClientRectangle, ForeColor,
                    TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine);
                if (Focused && ShowFocusCues)
                    ControlPaint.DrawFocusRectangle(e.Graphics, Rectangle.Inflate(bounds, -4, -4), ForeColor, bottom);
            }
        }
    }
}
