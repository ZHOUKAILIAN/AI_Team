import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        console: {
          canvas: "#eef2ef",
          surface: "#fffef8",
          muted: "#68736d",
          ink: "#162026",
          line: "#ccd6cf",
          green: "#0d766e",
          blue: "#255f86",
          amber: "#c3861a",
          red: "#b54238"
        }
      },
      boxShadow: {
        console: "0 24px 78px rgba(20, 30, 34, 0.16)"
      },
      fontFamily: {
        sans: ["Avenir Next", "PingFang SC", "Microsoft YaHei", "ui-sans-serif", "system-ui"]
      }
    }
  },
  plugins: []
} satisfies Config;
