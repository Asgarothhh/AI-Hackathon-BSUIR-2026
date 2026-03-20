import { exportFile } from "../../../api/file";

export default function ChatExportButton() {
    const handleClick = async () => {
        await exportFile()
    }
    return (
        <button
            onClick={handleClick}
            className="
        group w-fit relative inline-flex items-center gap-2
        px-6 py-3 rounded-xl
        bg-gradient-to-r from-indigo-500 to-blue-500
        text-white font-medium
        shadow-lg shadow-indigo-500/30
        
        transition-all cursor-pointer duration-300
        hover:shadow-xl hover:shadow-indigo-500/50
        hover:scale-[1.03]
        active:scale-[0.98]
      "
        >
            <span className="
        absolute inset-0 rounded-xl
        bg-gradient-to-r from-indigo-400 to-blue-400
        opacity-0 group-hover:opacity-30
        blur-xl transition duration-300
      " />

            <svg
                xmlns="http://www.w3.org/2000/svg"
                className="w-5 h-5 relative z-10"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
            >
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 16v-8m0 8l-3-3m3 3l3-3M4 20h16" />
            </svg>

            <span className="relative z-10">Экспорт</span>
        </button>
    );
}