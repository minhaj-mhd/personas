from typing import List, Union

def assemble_system_prompt(
    name: str,
    description: str,
    personality_traits: Union[List[str], str, None],
    speaking_style: str | None,
    goals: str | None,
    constraints: str | None,
    domain_expertise: str | None
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
