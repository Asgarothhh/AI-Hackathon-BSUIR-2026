import { useModal } from "../../../contexts/ModalContext";
import LoginModal from "../../blocks/auth/LoginModal";

export default function HeaderAccount() {
    const { openModal } = useModal();

    const handleOpen = () => {
        openModal(<LoginModal />);
    };

    return (
        <div onClick={handleOpen}>
            <img src="/auth.png" alt="" />
        </div>
    )
}