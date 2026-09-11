"""RAG (Retrieval-Augmented Generation) : répondre à partir des documents de l'utilisateur.

Indexation : texte extrait → découpé en morceaux → chaque morceau devient un vecteur.
Question : vecteur de la question → morceaux les plus proches → ajoutés au prompt.
"""
