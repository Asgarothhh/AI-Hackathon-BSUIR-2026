import type { ChangeEvent } from "react";

interface FormGroupInterface {
    id: string;
    type?: string;
    prefix?: string;
    value: string;
    onChange: (value: string) => void;
}

export default function FormGroup({
    id,
    type = "text",
    value,
    onChange,
}: FormGroupInterface) {
    const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
        let inputVal = e.target.value;

        onChange(inputVal);
    };

    return (
        <input
            className="outline-0 border-2 border-[#5463BC] rounded-[25px] p-5 text-lg"
            id={id}
            name={id}
            type={type}
            value={value}
            onChange={handleChange}
        />
    );
}