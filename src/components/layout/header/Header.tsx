import { Link } from "react-router-dom";
import Container from "../../shared/container/Container";
import HeaderAccount from "./HeaderAccount";

export default function Header() {
    return (
        <header className="w-full h-25 grid-col-[1/3]">
            <Container>
                <div className="flex justify-between items-center">
                    <h1 className="text-[20px] text-white">
                        <Link to={"/"}>
                        Cognify Law Engine
                        </Link>
                    </h1>
                    <HeaderAccount/>
                </div>
            </Container>
        </header>  
    )
}