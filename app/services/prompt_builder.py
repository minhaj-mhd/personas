from typing import List, Union


def assemble_system_prompt(
    name: str,
    description: str,
    personality_traits: Union[List[str], str, None],
    speaking_style: str | None,
    goals: str | None,
    constraints: str | None,
    domain_expertise: str | None,
) -> str:
    """
    Assembles a structured system prompt from persona characteristics.
    """
    if isinstance(personality_traits, list):
        traits_prose = ", ".join(personality_traits)
    else:
        traits_prose = personality_traits or "Balanced and helpful"

    prompt = f"You are {name}, {description}.\n"
    prompt += f"PERSONALITY: {traits_prose}\n"

    if speaking_style:
        prompt += f"SPEAKING STYLE: {speaking_style}\n"
    if goals:
        prompt += f"GOALS: {goals}\n"
    if constraints:
        prompt += f"CONSTRAINTS: {constraints}\n"
    if domain_expertise:
        prompt += f"DOMAIN EXPERTISE: {domain_expertise}\n"

    prompt += (
        "\nAlways stay in character. Keep spoken responses natural and conversational "
        "(1-4 sentences unless asked to elaborate), since the user is talking, not reading."
    )
    return prompt


def format_retrieved_memories(memories: list) -> str:
    """
    Formats narrative summaries and retrieved semantic facts/documents into a string block.
    """
    if not memories:
        return ""

    summaries = []
    facts_and_docs = []

    for mem in memories:
        if mem.memory_type == "summary":
            summaries.append(mem.content)
        else:
            prefix = ""
            if (
                hasattr(mem, "metadata_")
                and mem.metadata_
                and "source" in mem.metadata_
            ):
                prefix = f"[{mem.metadata_['source']}]: "
            facts_and_docs.append(f"- {prefix}{mem.content}")

    injected = "### LONG-TERM MEMORY & CONTEXT\n"

    if summaries:
        injected += f"Narrative Summary of Past Conversations:\n{summaries[0]}\n\n"

    if facts_and_docs:
        injected += "Extracted Facts & Uploaded Reference Materials:\n"
        injected += "\n".join(facts_and_docs) + "\n"

    return injected.strip()


def inject_memories_into_prompt(base_prompt: str, memories: list) -> str:
    """
    Injects narrative summaries and retrieved semantic facts/documents into the base prompt.
    """
    memory_block = format_retrieved_memories(memories)
    if memory_block:
        return base_prompt + "\n\n" + memory_block
    return base_prompt
