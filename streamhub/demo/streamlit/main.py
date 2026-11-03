import streamlit as st


def main():
    st.title("Hello World!")
    st.write("This is a hello world! streamlit app.")
    name = st.text_input("Your name", "Streamhub")
    st.write(f"Hello, {name}!")
    user = st.context.headers.get("X-Streamhub-User")
    st.caption(f"Signed in to Streamhub as {user}" if user else "Not signed in to Streamhub")


if __name__ == "__main__":
    main()
