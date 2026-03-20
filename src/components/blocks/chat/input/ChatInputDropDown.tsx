import { useState } from "react";

export default function ChatInputDropDown() {
    const [isOpen, setIsOpen] = useState(false);
    const [selected, setSelected] = useState("Анализ");

    const options = ["Анализ", "Создание БЗ"];

    const handleSelect = (option: string) => {
        setSelected(option);
        setIsOpen(false);
    };

    return (
        <div style={{ boxShadow: "0px 4px 4px 0px #00000040" }} className="relative text-left w-40 h-17.5 flex justify-center rounded-[25px] cursor-pointer p-5 px-2 bg-[#5463BC]">
            <button
                onClick={() => setIsOpen((prev) => !prev)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md hover:bg-blue focus:outline-none"
            >
                <span>{selected}</span>
                <img
                    src="/icon/input/dropdown.svg"
                    alt=""
                    className={`transition-transform duration-200 ${isOpen ? "rotate-180" : "rotate-0"
                        }`}
                />
            </button>

            {isOpen && (
                <div className="absolute top-18.5 mt-1 w-40 bg-[#6B76B473] rounded-md shadow-md z-100">
                    {options.map((option) => (
                        <button
                            key={option}
                            onClick={() => handleSelect(option)}
                            className={`block w-full text-left px-3 py-2 text-sm hover:bg-[#6b76b4] ${selected === option ? "bg-[#6b76b4] font-medium" : ""
                                }`}
                        >
                            {option}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}